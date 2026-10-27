# Security boundary

The core evaluates only fixed reviewed integer comparison templates and bounded typed policy-v1 JSON predicates. Policy/session imports reject unknown fields, duplicate keys/IDs, unsafe prototype keys, markup-like category values, excessive sizes and invalid history. Python and JavaScript use a versioned contract with paired parity checks. Digests bind inputs but do not authenticate their reviewer. It does not execute arbitrary supplied code. The CLI only exports a contract for an explicit module:function and never imports that target. Running an export is an explicit operator action: Python imports execute code, and exported tests are not a sandbox. Use reviewed implementations in an appropriate execution environment.

Keep sensitive requirements, labels and implementation data local. The browser launcher binds only to 127.0.0.1 and serves only its static web directory. The UI has no telemetry, browser storage or provider integration. It is a local demo, not an authenticated service. Do not expose it through a public listener.

For a suspected vulnerability, use the repository host's private reporting channel when available, or contact the maintainer privately. Include a minimal synthetic reproducer without secrets or personal data. No certification or production security claim is made.

Explicit CLI inputs must be regular files. Symlinks to regular files are supported. On POSIX, nonblocking descriptor open followed by fstat rejects FIFOs, devices and directories before reading, without a separate path-check/open race. Input-open diagnostics do not reveal file paths or values. Existing byte and JSON limits still apply. This does not promise a deadline for a slow regular filesystem.
