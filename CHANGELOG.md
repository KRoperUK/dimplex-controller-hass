# Changelog

## [3.0.0](https://github.com/KRoperUK/dimplex-controller-hass/compare/v2.0.0...v3.0.0) (2026-07-13)


### ⚠ BREAKING CHANGES

* open-window switch, provisioning diagnostics, and entity docs ([#81](https://github.com/KRoperUK/dimplex-controller-hass/issues/81))

### Features

* accurate energy reporting with T1 telemetry + fix reload loop ([#61](https://github.com/KRoperUK/dimplex-controller-hass/issues/61)) ([993dbbe](https://github.com/KRoperUK/dimplex-controller-hass/commit/993dbbed9b56bfba6f0b67f6d957af85ee18edb6))
* add energy monitoring sensor ([#48](https://github.com/KRoperUK/dimplex-controller-hass/issues/48)) ([f580374](https://github.com/KRoperUK/dimplex-controller-hass/commit/f580374396382cd55aa30f46d097ebe5b181a5a5))
* **assets:** add brand assets ([#53](https://github.com/KRoperUK/dimplex-controller-hass/issues/53)) ([203f7d8](https://github.com/KRoperUK/dimplex-controller-hass/commit/203f7d8ce9c270f3011f09d92e4b3a39e792955d))
* capability-aware climate + boost duration ([#108](https://github.com/KRoperUK/dimplex-controller-hass/issues/108)) ([a9d035b](https://github.com/KRoperUK/dimplex-controller-hass/commit/a9d035bc865a71cf6aa6adabc9d2de6f8b4b640e))
* **ci:** semver pre-release versions for HACS dev builds ([#84](https://github.com/KRoperUK/dimplex-controller-hass/issues/84)) ([5768e32](https://github.com/KRoperUK/dimplex-controller-hass/commit/5768e320dc013fc4d7667a95b70e5d99f45570b2))
* climate entity, daily/lifetime energy, split coordinators ([#78](https://github.com/KRoperUK/dimplex-controller-hass/issues/78)) ([25a054b](https://github.com/KRoperUK/dimplex-controller-hass/commit/25a054b7f2c94e92c89d9a252bbc446070881ff1))
* config entry diagnostics download (redacted) ([#103](https://github.com/KRoperUK/dimplex-controller-hass/issues/103)) ([4842360](https://github.com/KRoperUK/dimplex-controller-hass/commit/48423600f35a7dc49a97b85191c73050f7c95e27)), closes [#91](https://github.com/KRoperUK/dimplex-controller-hass/issues/91)
* domain services and repairs ([#107](https://github.com/KRoperUK/dimplex-controller-hass/issues/107)) ([309b83e](https://github.com/KRoperUK/dimplex-controller-hass/commit/309b83ec4276bc076a459a19dca68ca156f8981f))
* enrich device registry with serial and firmware metadata ([#65](https://github.com/KRoperUK/dimplex-controller-hass/issues/65)) ([a8aa20b](https://github.com/KRoperUK/dimplex-controller-hass/commit/a8aa20bbf05550eb4a96a86142d76ff07cbdbb09))
* estimated power diagnostic and adaptive energy polling ([#106](https://github.com/KRoperUK/dimplex-controller-hass/issues/106)) ([5d095ef](https://github.com/KRoperUK/dimplex-controller-hass/commit/5d095ef6c959757472e3444f6e68b14d3168b1dd)), closes [#95](https://github.com/KRoperUK/dimplex-controller-hass/issues/95) [#96](https://github.com/KRoperUK/dimplex-controller-hass/issues/96)
* move hardcoded entity icons into icons.json ([#139](https://github.com/KRoperUK/dimplex-controller-hass/issues/139)) ([eea51b0](https://github.com/KRoperUK/dimplex-controller-hass/commit/eea51b0777ba7a1a79e815b23f813c66060d1e76)), closes [#131](https://github.com/KRoperUK/dimplex-controller-hass/issues/131)
* open-window switch, provisioning diagnostics, and entity docs ([#81](https://github.com/KRoperUK/dimplex-controller-hass/issues/81)) ([e4ac815](https://github.com/KRoperUK/dimplex-controller-hass/commit/e4ac815e4209fd1d38cd6657ba1500bf6e61fd28))
* prevent adding the same Dimplex account twice ([#124](https://github.com/KRoperUK/dimplex-controller-hass/issues/124)) ([3a99d70](https://github.com/KRoperUK/dimplex-controller-hass/commit/3a99d702fbcd6e80083f55f0364a9b5aca9e4f49))
* schedule read, zone devices, blueprints, multi-config docs ([#109](https://github.com/KRoperUK/dimplex-controller-hass/issues/109)) ([0a5375a](https://github.com/KRoperUK/dimplex-controller-hass/commit/0a5375a0f9b634d3d1b9cef66ba1a00dc29a3654))


### Bug Fixes

* bump dimplex-controller to &gt;=0.6.1; update energy telemetry docs ([#64](https://github.com/KRoperUK/dimplex-controller-hass/issues/64)) ([cab3dbd](https://github.com/KRoperUK/dimplex-controller-hass/commit/cab3dbd5ac732d71def0337092a933629aca8113))
* **ci:** roll over main RC tags when an RC number is already burned ([#80](https://github.com/KRoperUK/dimplex-controller-hass/issues/80)) ([37b83fc](https://github.com/KRoperUK/dimplex-controller-hass/commit/37b83fc550aa2504c813a3ffb13e6de5fbfd18ae))
* **ci:** stop force-pushing unsigned RC commits to dev ([#87](https://github.com/KRoperUK/dimplex-controller-hass/issues/87)) ([fa6f631](https://github.com/KRoperUK/dimplex-controller-hass/commit/fa6f63196d8adff782630f6fe8b97f864ff48ef8))
* **ci:** treat scripts changes as component-impacting ([#90](https://github.com/KRoperUK/dimplex-controller-hass/issues/90)) ([9fb07be](https://github.com/KRoperUK/dimplex-controller-hass/commit/9fb07be5e493d2153261fab17216c3f382aa16d5))
* **ci:** write HACS zip to absolute path ([#89](https://github.com/KRoperUK/dimplex-controller-hass/issues/89)) ([37bb091](https://github.com/KRoperUK/dimplex-controller-hass/commit/37bb0910269dd6fb942dd6cacffe19140e9e5331))
* declare _summary_cached/_summary_ts types to satisfy mypy ([#140](https://github.com/KRoperUK/dimplex-controller-hass/issues/140)) ([ac80b3d](https://github.com/KRoperUK/dimplex-controller-hass/commit/ac80b3d069e651bb9add1cfaec813f342fe59786))
* degrade energy report API errors gracefully instead of CannotConnect ([#59](https://github.com/KRoperUK/dimplex-controller-hass/issues/59)) ([c0696de](https://github.com/KRoperUK/dimplex-controller-hass/commit/c0696debc8d74291f8830e3b4e7ada336bde9c43))
* fallback to individual appliance overview queries on bulk failure ([#55](https://github.com/KRoperUK/dimplex-controller-hass/issues/55)) ([dfdbe4e](https://github.com/KRoperUK/dimplex-controller-hass/commit/dfdbe4e3b62eafd723dfd3d17a330a132f2b904e))
* **hacs:** ship dimplex.zip release assets for reliable installs ([#88](https://github.com/KRoperUK/dimplex-controller-hass/issues/88)) ([a2e9f6b](https://github.com/KRoperUK/dimplex-controller-hass/commit/a2e9f6bda3023d79a9c3f9f0c5be5573f3d9c7bb))
* keep T1 and T2 energy separate (no combined total) ([#110](https://github.com/KRoperUK/dimplex-controller-hass/issues/110)) ([9e42394](https://github.com/KRoperUK/dimplex-controller-hass/commit/9e423942ad356407193b3577c60bf028cd8a383e))
* parenthesise except in climate._boost_minutes and pin ruff ([#112](https://github.com/KRoperUK/dimplex-controller-hass/issues/112)) ([56285ce](https://github.com/KRoperUK/dimplex-controller-hass/commit/56285ce2a938c0e634186b13ce4154dad56d13de))
* parenthesize multi-type except for Python 3 ([#79](https://github.com/KRoperUK/dimplex-controller-hass/issues/79)) ([170e213](https://github.com/KRoperUK/dimplex-controller-hass/commit/170e213a2f2c1f2f86de31be0087991f7403f060))
* refresh status after control services so state updates promptly ([#125](https://github.com/KRoperUK/dimplex-controller-hass/issues/125)) ([5db4e8c](https://github.com/KRoperUK/dimplex-controller-hass/commit/5db4e8c17370c6accc9ffc73cdc29fd0dbd13d6e))
* replace module-global _SKIP_RELOAD_ENTRY_IDS with options-diff ([#138](https://github.com/KRoperUK/dimplex-controller-hass/issues/138)) ([389d3cc](https://github.com/KRoperUK/dimplex-controller-hass/commit/389d3ccea3322d310cc6abe876f061753958763b)), closes [#130](https://github.com/KRoperUK/dimplex-controller-hass/issues/130)
* require dimplex-controller&gt;=0.8.0 and document 3.0.0 upgrade ([#82](https://github.com/KRoperUK/dimplex-controller-hass/issues/82)) ([ded06c5](https://github.com/KRoperUK/dimplex-controller-hass/commit/ded06c51f938f55e11e2f21f2667672aafc79c15))
* resolve all six open dimplex-controller-hass issues ([#120](https://github.com/KRoperUK/dimplex-controller-hass/issues/120)) ([8e47cff](https://github.com/KRoperUK/dimplex-controller-hass/commit/8e47cff7af6fdcb5b6942524511ee79603eb2f65))
* use TOTAL_INCREASING for lifetime energy sensors ([#134](https://github.com/KRoperUK/dimplex-controller-hass/issues/134)) ([d2f3fc7](https://github.com/KRoperUK/dimplex-controller-hass/commit/d2f3fc751bb674702b001ad7b04c14a8df068272)), closes [#127](https://github.com/KRoperUK/dimplex-controller-hass/issues/127)


### Performance Improvements

* cache energy summary per coordinator update cycle ([#136](https://github.com/KRoperUK/dimplex-controller-hass/issues/136)) ([a9c554e](https://github.com/KRoperUK/dimplex-controller-hass/commit/a9c554e223215a41a99e2fdf1244386be9ea8fd1)), closes [#128](https://github.com/KRoperUK/dimplex-controller-hass/issues/128)
* fetch timer schedules on a slow cadence instead of every status poll ([#123](https://github.com/KRoperUK/dimplex-controller-hass/issues/123)) ([b543c37](https://github.com/KRoperUK/dimplex-controller-hass/commit/b543c378747e8c8ac15648b768723ac74c58cccd))

## [2.0.0](https://github.com/KRoperUK/dimplex-controller-hass/compare/v1.1.1...v2.0.0) (2026-06-22)


### ⚠ BREAKING CHANGES

* add username/password credential auth to config flow ([#37](https://github.com/KRoperUK/dimplex-controller-hass/issues/37))

### Features

* add username/password credential auth to config flow ([#37](https://github.com/KRoperUK/dimplex-controller-hass/issues/37)) ([e4bef7e](https://github.com/KRoperUK/dimplex-controller-hass/commit/e4bef7eddce4c3204101df26e08a8af122a78fab))


### Bug Fixes

* require dimplex-controller&gt;=0.3.0 for headless login support ([#39](https://github.com/KRoperUK/dimplex-controller-hass/issues/39)) ([6f33a0d](https://github.com/KRoperUK/dimplex-controller-hass/commit/6f33a0d98bebd1a4c9c2e4af0ad26928322aedec))

## [1.1.1](https://github.com/KRoperUK/dimplex-controller-hass/compare/v1.1.0...v1.1.1) (2026-06-22)


### Bug Fixes

* add MOCK_ENTRY_DATA import for reauth tests ([#35](https://github.com/KRoperUK/dimplex-controller-hass/issues/35)) ([8db6f3d](https://github.com/KRoperUK/dimplex-controller-hass/commit/8db6f3d7a551551d551d95b3b0dcd1eb0a2c2c3d))
* implement reauth config flow to allow token refresh on expiry ([#32](https://github.com/KRoperUK/dimplex-controller-hass/issues/32)) ([c71b002](https://github.com/KRoperUK/dimplex-controller-hass/commit/c71b0025d1279eeb27af8a2a37ea34870d41ba5f)), closes [#29](https://github.com/KRoperUK/dimplex-controller-hass/issues/29)
* restore async_setup_entry function signature ([#34](https://github.com/KRoperUK/dimplex-controller-hass/issues/34)) ([280061e](https://github.com/KRoperUK/dimplex-controller-hass/commit/280061e32870ea4c41f65c7465675cf6fa0773cc))
* revert entity IDs to match CI test environment ([#36](https://github.com/KRoperUK/dimplex-controller-hass/issues/36)) ([e0be792](https://github.com/KRoperUK/dimplex-controller-hass/commit/e0be792750c1fda6d0266272b6f29299ff7022ff))

## [1.1.0](https://github.com/KRoperUK/dimplex-controller-hass/compare/v1.0.0...v1.1.0) (2026-06-10)


### Features

* add state-aware icons for EcoStart and Comfort entities ([#23](https://github.com/KRoperUK/dimplex-controller-hass/issues/23)) ([01ae73b](https://github.com/KRoperUK/dimplex-controller-hass/commit/01ae73b9efa8b769bff044a564fc9f17a6115bc0)), closes [#7](https://github.com/KRoperUK/dimplex-controller-hass/issues/7)


### Bug Fixes

* prettier ignore changelog ([#3](https://github.com/KRoperUK/dimplex-controller-hass/issues/3)) ([b286bef](https://github.com/KRoperUK/dimplex-controller-hass/commit/b286bef41789baa5234655d5932ea03677f99192))

## 1.0.0 (2026-02-17)


### Features

* **ci:** add linting and testing workflows ([#1](https://github.com/KRoperUK/dimplex-controller-hass/issues/1)) ([f580610](https://github.com/KRoperUK/dimplex-controller-hass/commit/f5806109c20d53f2c73ebd3fd4c053c20d3ecbeb))
* initial ([1a218f7](https://github.com/KRoperUK/dimplex-controller-hass/commit/1a218f709a85f660800e9e77a87b2a6ac6b1e8da))
