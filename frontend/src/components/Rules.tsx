const bands = ['Up to 5 million', 'Above 5, up to 10 million', 'Above 10, up to 25 million',
  'Above 25, up to 50 million', 'Above 50, up to 75 million', 'Above 75, up to 100 million',
  'Above 100, up to 125 million', 'Above 125, up to 150 million', 'Above 150 million'];

/** Approved brief plus implemented A-H conventions. No gameplay calculations run here. */
export function Rules() {
  return <article className="geo-rules" aria-labelledby="rules-title">
    <header className="geo-page-heading"><span className="geo-label">How to play</span><h2 id="rules-title">One country to begin. Ten to win.</h2>
      <p>Geopolitics is a single-player game against nine strategic NPC opponents. These rules describe the game you can play here.</p></header>
    <nav aria-label="Rules sections"><a href="#rules-setup">Setup</a><a href="#rules-turn">Your turn</a><a href="#rules-battle">Battles</a>
      <a href="#rules-conquest">Conquest</a><a href="#rules-rounds">New rounds</a><a href="#rules-watch">Watching</a></nav>
    <section id="rules-setup"><h3>Choose your starting country</h3><p>Choose one canonical country. The server randomly selects nine distinct rivals and saves a randomized turn order; the human is not guaranteed to go first. Each participant starts with one country.</p>
      <table><caption>Population-based starting soldiers</caption><thead><tr><th scope="col">Population</th><th scope="col">Soldiers</th></tr></thead>
        <tbody>{bands.map((label, index) => <tr key={label}><td>{label}</td><td>{index + 1}</td></tr>)}</tbody></table>
    </section>
    <section id="rules-turn"><h3>On your turn</h3><p>Allocate any reinforcements first. Then choose one opposing country to attack, or skip your turn. You may attack any rival country regardless of distance. Your attacking country must hold at least two soldiers.</p>
      <p>Outside an ongoing battle, transfer positive whole numbers of soldiers between two different countries you hold. Leave at least one soldier in the source. A transfer does not start an attack.</p></section>
    <section id="rules-battle"><h3>Every dice pair matters</h3><p>Starting an attack locks the source and target; it does not roll dice. Choose Roll battle dice for each exchange.</p>
      <p>Each side rolls the smaller of the attacker's soldiers minus one and the defender's soldiers. There is no three-dice cap. Dice are paired in their original order, without sorting: first with first, second with second, and so on.</p>
      <p>The lower roll in each pair loses one soldier. Ties cause no loss. Losses are applied together. You may repeat exchanges against the same target until conquest, until only one attacking soldier remains, or until you stop. Choosing Stop attack ends your turn.</p></section>
    <section id="rules-conquest"><h3>Conquest and transfer</h3><p>When the defending country loses its last soldier, ownership changes immediately. Its reward is the greater of two soldiers or half its original population-based soldier value, rounded down. The reward is placed in the captured country automatically.</p>
      <p>Surviving attackers stay in their source country. You may make an optional positive transfer while leaving one behind, then choose End turn. There is no separate conquest-confirmation step and no second attack that turn. A forced failed attack also allows transfers and End turn.</p>
      <p>Conquering the final country wins immediately; no extra turn-ending action is needed.</p></section>
    <section id="rules-rounds"><h3>New rounds and NPC turns</h3><p>Round one has no reinforcements. From round two onward, at the start of your turn receive two soldiers for every country you hold. Allocate the entire pool among your countries before continuing.</p>
      <p>A participant holding no countries is eliminated and their future turns are skipped. The saved turn order still determines round boundaries. Hold all ten participating countries to win; there is no fixed round limit.</p>
      <p>NPCs choose attacks, transfers, allocations and when to stop using a shared strategy. Their recorded decisions and brief explanations appear in the Chronicle. Step advances one action; Fast-forward continues until the human turn, game completion or an interruption. Pause prevents another automatic action from starting; a submitted action may still finish.</p>
      <p>If the human is eliminated while the game remains active, its owner can continue the remaining NPC turns.</p></section>
    <section id="rules-watch"><h3>Watch, resume and read the record</h3><p>Sign in to create and play your own campaigns. My Games lets you resume saved games. A shared game link gives anyone read-only access; spectators cannot play or generate narration.</p>
      <p>Commentary is atmospheric narration from saved battle exchanges. Dice, losses, soldiers and ownership remain authoritative. Owner commentary is enabled for new eligible exchanges by default and can be turned off in Commentary settings. Saved history is not automatically regenerated.</p>
      <p>If a move's response is interrupted, keep the page open and use its recovery controls. Never assume an unknown outcome failed or submit a replacement move.</p></section>
    <p className="geo-help">Based on the UCT INF4001N 2027 brief and the project's approved turn, reward and transfer conventions.</p>
  </article>;
}
