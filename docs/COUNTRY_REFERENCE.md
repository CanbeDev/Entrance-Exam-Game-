# Country information reference - Stage 8.5

The final human scope reduction removes military history entirely. There is no
history dataset, historical narrative, event/date section or history-source UI.
This reference supports the compact country card only.

## Existing project data

- Canonical IDs/names/population: `backend/app/data/countries.json`, dataset
  `worldometer-2026-2026-10-19` (195 eligible countries).
- Initial soldiers in the neutral reference: the actual inclusive upper bounds
  read from `backend/app/engine/population_rules.py` at generation time. This is
  a display snapshot, not a second runtime gameplay implementation.
- Participating-country population, initial allocation, current soldiers and
  owner come from the saved PublicGame, taking precedence over the neutral
  catalog. Missing saved values stay unavailable.
- Flags: existing canonical ISO mapping and licensed local flag assets. Existing
  presentation aliases are reused; geometry and all seven fallback anchors are
  unchanged. Neutral countries have no current game soldiers or owner.

## Already verified capital source

Before the scope reduction, the public GeoNames countryInfo snapshot was retrieved
and its capital column inspected. It is retained as permitted by the final user
instruction. No new history research or dataset is part of this delivery.

- [GeoNames countryInfo](https://download.geonames.org/export/dump/countryInfo.txt)
- [GeoNames readme and licence](https://download.geonames.org/export/dump/readme.txt)
- [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
- Retrieved/checked: 2026-11-03; original local copy:
  `frontend/data/geonames-countryInfo.txt`.
- SHA-256: `79f8f59ea01cbb40438bf1856dd6c2ff201f03f8fc72d0530b2646aaf603ef04`.

The readme explicitly licenses the data under CC BY 4.0. GeoNames provides it
without a guarantee of accuracy, timeliness or completeness. The card credits
GeoNames without adding a source-link interface. This derived reference joins
the existing flag ISO codes to the source's ISO column; no fuzzy name matching.
Population is taken from the project's dataset, not GeoNames.

181 capital reference values are shown. The following 14 entries are deliberately
omitted because a single city would require additional constitutional,
administrative, disputed-status or transition context:

`benin`, `bolivia`, `cote-d-ivoire`, `equatorial-guinea`, `indonesia`, `israel`,
`malaysia`, `nauru`, `netherlands`, `south-africa`, `sri-lanka`,
`state-of-palestine`, `swaziland`, `switzerland`.

This omission is conservative, not a claim that these countries lack capitals.
The displayed label is Capital reference. Source matching is verified; an
independent current constitutional-capital audit is not claimed.

## Offline generation and validation

From `frontend/`:

```powershell
node scripts/build-country-reference.mjs --check
node --test tests/country-info.test.mjs
```

The generated `src/country/reference.generated.json` includes source hashes,
canonical names, populations, starting soldiers and qualified capital values.
The generator makes no network request and never imports or writes backend code.
Tests compare all 195 identities/populations, exact source ISO joins, inclusive
soldier bounds, aliases, flags, neutral/owner/target states, saved-value precedence,
missing fields, long names, clamped positioning, keyboard/dismissal markup and
absence of gameplay requests. These checks establish data consistency, not an
independent geopolitical fact certification.

Release reproducibility: checksums of the catalog and GeoNames text use canonical
CRLF regardless of checkout line endings. This preserves the existing recorded
identifiers and generated facts on LF/CRLF systems; the generator does not change
country values or regenerate data during `--check`.
