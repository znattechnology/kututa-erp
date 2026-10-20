# Imagem de produção: Odoo 20.0 (submódulo odoo/) + módulos próprios (custom_addons/)
FROM python:3.13-slim-bookworm

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ODOO_RC=/etc/odoo/odoo.conf

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates fontconfig libpq-dev libldap2-dev libsasl2-dev \
        libxml2-dev libxslt1-dev libjpeg62-turbo-dev zlib1g-dev libffi-dev \
        node-less npm xfonts-75dpi xfonts-base fonts-dejavu-core \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && npm install -g rtlcss \
    && rm -rf /var/lib/apt/lists/*

COPY odoo/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN useradd --system --create-home --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo \
    && mkdir -p /etc/odoo /mnt/extra-addons \
    && chown odoo: /var/lib/odoo

COPY --chown=odoo:odoo odoo /opt/odoo
COPY --chown=odoo:odoo custom_addons /mnt/extra-addons
COPY --chown=odoo:odoo docker/odoo.conf /etc/odoo/odoo.conf

USER odoo
EXPOSE 8069 8072
VOLUME ["/var/lib/odoo"]
ENTRYPOINT ["python", "/opt/odoo/odoo-bin"]
CMD ["-c", "/etc/odoo/odoo.conf"]
