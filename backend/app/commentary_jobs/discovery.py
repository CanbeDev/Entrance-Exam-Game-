"""Bounded receipt rescans, independent of gameplay commits and browser playback."""
from collections import deque
from pymongo.errors import PyMongoError

from app.commentary_jobs.storage import collection, unavailable
from app.security.errors import SecurityError
from app.services.public_game_service import _receipt


class MongoCommentaryReceiptSource:
    def __init__(self, database):
        self.database = database

    def head_revision(self, game_id):
        from bson import ObjectId
        try:
            game = collection(self.database, "games").find_one({"_id": ObjectId(game_id)}, {"revision": 1})
            revision = game["revision"]
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise ValueError
            return revision
        except (PyMongoError, ValueError, KeyError, TypeError):
            raise unavailable() from None

    def public_events(self, game_id, after_revision, limit, through_revision=None):
        try:
            revisions = {"$gt": after_revision}
            if through_revision is not None:
                revisions["$lte"] = through_revision
            return list(collection(self.database, "game_action_receipts").find({
                "game_id": game_id, "result.state.revision": revisions
            }).sort([("result.state.revision", 1)]).limit(limit))
        except PyMongoError:
            raise unavailable() from None


class ReceiptReconciler:
    def __init__(self, policies, receipts, jobs, commentary, settings, clock, saved_reconciler=None):
        self.policies, self.receipts, self.jobs = policies, receipts, jobs
        self.commentary, self.settings, self.clock = commentary, settings, clock
        self.after_game = ""
        self.pending = deque()
        self.saved_reconciler = saved_reconciler

    def run_once(self):
        if not self.settings.discovery_enabled:
            return 0
        if not self.pending:
            page = self.policies.enabled_page(self.after_game, self.settings.batch_size)
            if not page:
                self.after_game = ""
                return 0
            self.after_game = page[-1].game_id
            self.pending.extend((policy, policy.activation_revision - 1, None) for policy in page)
        policy, after, through = self.pending.popleft()
        count = 0
        try:
            # Deny stale policy versions/ownership/disabled accounts before discovery.
            context = self.policies.authorize(policy.game_id, max(after + 1, policy.activation_revision), "discovery")
            if context.policy_version != policy.version:
                return 0
            # Freeze this pass's upper bound so a continuously active game cannot
            # prevent enumeration of the next page of campaigns.
            if through is None:
                through = self.receipts.head_revision(policy.game_id)
            rows = self.receipts.public_events(policy.game_id, after, self.settings.batch_size, through)
            for row in rows:
                receipt = _receipt(row)
                revision = receipt.result.state.revision
                if receipt.game_id != policy.game_id or revision <= after:
                    raise SecurityError(503, "commentary_evidence_mismatch")
                if any(event.type == "dice_exchange" for event in receipt.result.events):
                    # Same battle parser as GET/POST, including exact dice/actor checks.
                    base = self.commentary._battle(policy.game_id, revision)
                    job = self.jobs.enqueue(base.game_id, revision, base.action_id, self.clock())
                    if self.saved_reconciler is not None and job.status == "failed":
                        self.saved_reconciler(base.game_id, revision)
                    count += 1
                after = revision
            if len(rows) == self.settings.batch_size and after < through:
                self.pending.append((policy, after, through))
            return count
        except SecurityError as error:
            if error.status in {401, 403}:
                return 0  # Removed consent must not pin the enumeration cursor.
            # A later full sweep retries this game's durable receipt boundary.
            # Drop this page's volatile cursor so other campaigns can progress.
            raise
