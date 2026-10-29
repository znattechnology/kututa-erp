# Imagem de produção: Odoo 20.0 (submódulo odoo/) + módulos próprios (custom_addons/)
FROM python:3.13-slim-bookworm

ARG WKHTMLTOPDF_VERSION=0.12.6.1-3
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependências de runtime + build; as de build são removidas depois do pip install.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates fontconfig xfonts-75dpi xfonts-base fonts-dejavu-core fonts-liberation \
        libpq5 libldap-2.5-0 libsasl2-2 libxml2 libxslt1.1 libjpeg62-turbo zlib1g libffi8 libcairo2 npm \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev \
        libjpeg62-turbo-dev zlib1g-dev libffi-dev libcairo2-dev pkg-config \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${ARCH}.deb" \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && rm -f /tmp/wkhtmltox.deb \
    && npm install -g rtlcss \
    && rm -rf /var/lib/apt/lists/*

COPY odoo/requirements.txt /tmp/requirements.txt
# rlPyCairo: backend de imagem do reportlab (códigos de barras e QR code da AGT); o pip não o inclui.
RUN pip install --no-cache-dir -r /tmp/requirements.txt rlPyCairo==0.4.0 \
    && apt-get purge -y --auto-remove \
        build-essential libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev \
        libjpeg62-turbo-dev zlib1g-dev libffi-dev libcairo2-dev pkg-config \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt

RUN useradd --system --create-home --home-dir /var/lib/odoo --shell /usr/sbin/nologin odoo \
    && mkdir -p /etc/odoo /mnt/extra-addons

# Código e configuração pertencem ao root (só leitura); só /var/lib/odoo é gravável pelo utilizador odoo.
COPY odoo /opt/odoo
# Temas oficiais do site (submódulo design-themes, LGPL).
COPY design-themes /opt/design-themes
COPY custom_addons /mnt/extra-addons
COPY docker/odoo.conf /etc/odoo/odoo.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

USER odoo
EXPOSE 8069 8072
VOLUME ["/var/lib/odoo"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -fsS http://127.0.0.1:8069/web/health || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
