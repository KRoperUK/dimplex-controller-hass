<!--
  Abbreviations used across the documentation.

  Appended to every page by pymdownx.snippets (`auto_append` in zensical.toml).
  With the `content.tooltips` theme feature, each entry below gets a hover
  definition wherever it appears — define once, works everywhere.

  Kept outside docs/ on purpose: zensical 0.0.62 has no `exclude_docs`, so a .md
  file inside the docs root would be published as its own page.

  THE RULE: abbreviations only, and only ones the documentation actually uses.
  Not ordinary words, however domain-specific they feel. Three reasons, all
  learned the hard way:

  1. Every occurrence on every page is styled and gets a tooltip. Entries for
     `Boost`, `Away` and `EcoStart` were underlined six to nine times per page,
     on the very pages that explain them at length. That is noise, not help.
  2. Matching is on the word, not the meaning. `Manual` was defined as the
     appliance timer mode, so it attached that definition to "Manual auth code"
     three times on the authentication page — where it was simply wrong.
  3. Entries for terms the prose never uses (`APK`, `DHW`, `HWC`, `TSI`) only
     misrepresent the vocabulary. Add one when you first write it.

  If a term is a word rather than an abbreviation, link to the page that defines
  it: modes in use/modes.md, energy registers in use/energy.md, hubs and zones in
  reference/entities.md.
-->

*[GDHV]: Glen Dimplex Heating & Ventilation, the manufacturer behind the Dimplex cloud.
*[HACS]: Home Assistant Community Store, the add-on manager used to install this integration.
*[T1]: The first of the cloud's two energy registers, observed to be the off-peak (cheaper) rate.
*[T2]: The second of the cloud's two energy registers, observed to be the peak (more expensive) rate. Never summed with T1.
