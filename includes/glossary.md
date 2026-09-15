<!--
  Glossary of Dimplex and Home Assistant vocabulary.

  Appended to every documentation page by pymdownx.snippets (`auto_append` in
  zensical.toml). With the `content.tooltips` theme feature, each term below
  gets a hover definition wherever it appears in the prose — define once, works
  everywhere, no per-page markup.

  Kept outside docs/ on purpose: zensical 0.0.62 has no `exclude_docs`, so a
  .md file inside the docs root would be published as its own page.

  Only add terms whose meaning is genuinely non-obvious or Dimplex-specific.
  An abbreviation defined here is styled on every page, so a common English
  word would produce noise on every occurrence.
-->

*[Advance]: Skips forward to the next scheduled comfort period, bringing its setpoint on early, then hands control back to the schedule. Not a fixed-duration override.
*[APK]: The Android application package for the official Dimplex Control app, from which this integration's protocol knowledge was reverse-engineered.
*[Away]: A settable setback temperature (7-18 °C) held until a date you choose. Distinct from frost protection, which is fixed at 7 °C.
*[Boost]: A temporary override to a higher target for a fixed number of minutes, after which the appliance returns to its schedule.
*[DHW]: Domestic hot water.
*[EcoStart]: A pre-heat setting that learns how long the room takes to warm and starts early so it reaches target on time. A setting, not an appliance mode.
*[Frost protection]: The 7 °C anti-freeze floor. Because Dimplex appliances have no off mode, this is what "off" means for both the official app and this integration.
*[GDHV]: Glen Dimplex Heating & Ventilation, the manufacturer behind the Dimplex cloud.
*[HACS]: Home Assistant Community Store, the add-on manager used to install this integration.
*[HWC]: Hot water cylinder.
*[Hub]: The Dimplex gateway device that relays between your appliances and the cloud. One hub, many zones, many appliances.
*[Manual]: A timer mode in which the appliance holds a single target and ignores its schedule.
*[Setback]: A reduced target temperature held during periods the schedule treats as unoccupied.
*[T1]: The first of two cloud energy registers, observed to be the off-peak (cheaper) rate.
*[T2]: The second cloud energy register, observed to be the peak (more expensive) rate. Never summed with T1.
*[TSI]: The cloud's telemetry reporting service, source of the daily kWh energy history.
*[Zone]: A grouping of appliances beneath a hub, usually one room or area.
