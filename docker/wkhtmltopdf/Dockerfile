# Desenvolvimento em macOS arm64: o wkhtmltopdf da produção (docker/Dockerfile) numa imagem própria,
# chamado pelo Odoo local através de tools/bin/wkhtmltopdf.
FROM debian:bookworm-slim

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates fontconfig xfonts-75dpi xfonts-base fonts-dejavu-core fonts-liberation \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

ENTRYPOINT ["wkhtmltopdf"]
