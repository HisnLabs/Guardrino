# Rust client example

Check a message with Guardrino's inspect API (`POST /v1/inspect`) from a Rust app, then send the model only what
Guardrino allows: the original text, the masked text, or nothing.

```sh
GUARDRINO_URL=https://guardrino.your-company.example cargo run -- "My Emirates ID is 784-1990-1234567-1"
cargo test
```

The Guardrino gateway itself is written in Rust and is a commercial product; this example only calls its API.
