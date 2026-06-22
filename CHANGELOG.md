# Changelog

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
