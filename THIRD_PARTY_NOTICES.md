# Third-party notices

RoamSync uses open-source packages through its Python, TypeScript, and Android
dependency lock files. Their respective licenses remain with their authors.

## Product references (not incorporated)

- TREK (AGPL-3.0): interaction and information-architecture research only. No
  TREK source code, styles, images, icons, or branding are included.
- Wanderlog, Google Maps, and TripIt: public product behavior was reviewed; no
  proprietary source code or assets are included.
- MapLibre and Organic Maps: public map-layer concepts were reviewed; neither
  project is currently bundled as a runtime dependency.
- FloatTrip (MIT), Tripper (Apache-2.0), TravelPlanner (MIT), and LangGraph:
  public Agent architecture and evaluation patterns were reviewed. No source
  code, prompts, datasets, or assets from these projects are incorporated by
  this change. Any future code adoption requires a pinned commit and a separate
  attribution review.

This file must be updated when a new dependency requiring attribution is added.

## Runtime Agent dependencies

- LangGraph (MIT) is used to model the resumable planning state machine.
- LangGraph Checkpoint PostgreSQL (MIT) stores durable graph checkpoints in the
  existing RoamSync PostgreSQL database.
- OpenAI Python SDK (Apache-2.0) provides the typed client used against the
  configured Responses API endpoint, including DeepSeek's compatible endpoint.
