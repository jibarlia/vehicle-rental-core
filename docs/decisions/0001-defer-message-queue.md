# ADR 0001: Defer message-queue infrastructure

- **Status:** Accepted
- **Date:** 2026-08-27

## Context

The project brief recommends message-queue communication as an optional extension. The
required operations are adding and updating vehicles, starting rentals, and completing
rentals. Each command must return a definitive result, and rental state changes must be
committed atomically with the related vehicle state.

Async FastAPI and database I/O improve concurrency, but they do not require an
event-driven workflow. No current requirement includes expensive background work or an
independent consumer that would justify operating a broker.

## Decision

The core transactional flow will remain request-response based, and the current runtime
will not include RabbitMQ or Kafka.

Messaging will be added only behind an application-owned outbound port. Its
infrastructure adapter will write to a transactional PostgreSQL outbox in the same
transaction as the related business change. A separately deployed relay will publish
committed messages, keeping broker availability out of the request path.

Two independent future stages are defined:

1. RabbitMQ for asynchronous report-generation commands.
2. Kafka for domain events consumed by a future audit service with its own database.

The detailed flows are documented in the
[messaging roadmap](../architecture/messaging-roadmap.md).

## Consequences

### Positive

- The current solution stays proportional to its requirements.
- Rental consistency and API semantics remain straightforward.
- Domain and application code remain independent of broker libraries.
- A future broker outage will not block a committed rental operation.
- The transactional outbox provides a reliable path from database commits to eventual
  publication.

### Trade-offs

- Messaging behavior is documented but not demonstrated in the current runtime.
- A later implementation must add the outbox schema, relay, broker deployment,
  idempotent consumers, retries, dead-letter handling, and monitoring.
- Transactional outbox delivery is at least once, so consumers must tolerate
  duplicates.

## Alternatives considered

### Route rental commands through a broker

Rejected because callers need an immediate business result and because it would make a
simple transactional operation depend on queue availability and asynchronous consumer
state.

### Publish directly to a broker during the HTTP request

Rejected because the PostgreSQL transaction and broker publication cannot commit
atomically. Either side can succeed while the other fails, producing missing or
incorrect messages.

### Add a broker with an artificial consumer now

Rejected because it would increase deployment and failure complexity without serving a
real workflow. Preserving the boundary and documenting the evolution is more useful
than introducing unused infrastructure.
