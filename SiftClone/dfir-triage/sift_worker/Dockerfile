FROM rust:bookworm AS hayabusa-builder

ARG HAYABUSA_VERSION=v3.9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch ${HAYABUSA_VERSION} --recursive https://github.com/Yamato-Security/hayabusa.git /opt/hayabusa \
    && cd /opt/hayabusa \
    && cargo build --release


FROM digitalsleuth/sift-docker:jammy

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        yara \
    && rm -rf /var/lib/apt/lists/*

COPY --from=hayabusa-builder /opt/hayabusa /opt/hayabusa

RUN printf '#!/usr/bin/env bash\ncd /opt/hayabusa\nexec /opt/hayabusa/target/release/hayabusa "$@"\n' > /usr/local/bin/hayabusa \
    && chmod +x /usr/local/bin/hayabusa \
    && yara --version \
    && hayabusa help >/dev/null
