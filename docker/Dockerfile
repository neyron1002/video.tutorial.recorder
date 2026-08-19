# Contenedor de desarrollo para grabar video tutoriales.
# Incluye: Claude Code, Codex CLI, Gemini CLI, Python + Playwright (Chromium),
# ffmpeg, edge-tts y una pantalla virtual X (Xvfb).
#
# La autenticación de los agentes es EFÍMERA: no se monta ningún directorio de
# credenciales del host. Al eliminar el contenedor se pierde la sesión.
FROM ubuntu:24.04

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
ARG NODE_MAJOR=22
ARG TZ=America/Mexico_City

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=${TZ} \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VTR_IN_CONTAINER=1

# --------------------------------------------------------------------------- #
# Sistema base: herramientas, Python, multimedia y servidor X virtual
# --------------------------------------------------------------------------- #
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg git git-lfs openssh-client \
        jq ripgrep unzip zip less nano vim-tiny procps psmisc tini sudo \
        bash-completion locales tzdata \
        build-essential pkg-config \
        python3 python3-venv python3-dev python3-pip \
        ffmpeg \
        xvfb x11-utils x11-xserver-utils xauth dbus-x11 \
        fonts-liberation fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji \
    && ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------- #
# Node.js + CLIs de agentes de IA
# --------------------------------------------------------------------------- #
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g --no-fund --no-audit \
        @anthropic-ai/claude-code \
        @openai/codex \
        @google/gemini-cli \
    && npm cache clean --force

# --------------------------------------------------------------------------- #
# Entorno Python: Playwright + edge-tts
# --------------------------------------------------------------------------- #
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN python3 -m venv ${VIRTUAL_ENV} \
    && pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt \
    && chmod -R a+rx ${PLAYWRIGHT_BROWSERS_PATH}

# --------------------------------------------------------------------------- #
# La herramienta `vtr`
# --------------------------------------------------------------------------- #
COPY pyproject.toml README.md /opt/vtr/
COPY src /opt/vtr/src
RUN pip install --no-cache-dir /opt/vtr

# --------------------------------------------------------------------------- #
# Usuario sin privilegios (el uid/gid se alinea con el del host)
# --------------------------------------------------------------------------- #
RUN if getent passwd ${USER_UID} >/dev/null; then \
        userdel -r "$(getent passwd ${USER_UID} | cut -d: -f1)" 2>/dev/null || true; \
    fi \
    && if ! getent group ${USER_GID} >/dev/null; then groupadd -g ${USER_GID} ${USERNAME}; fi \
    && useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash ${USERNAME} \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME} \
    && chown -R ${USER_UID}:${USER_GID} ${VIRTUAL_ENV} \
    && mkdir -p /workspace && chown ${USER_UID}:${USER_GID} /workspace

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER ${USERNAME}
WORKDIR /workspace

# Directorios de configuración de los agentes: viven solo dentro del contenedor.
ENV HOME=/home/${USERNAME} \
    NPM_CONFIG_PREFIX=/home/${USERNAME}/.npm-global \
    DISPLAY=:99 \
    SCREEN_SIZE=1920x1080x24 \
    VTR_NO_SANDBOX=1
ENV PATH=/home/${USERNAME}/.npm-global/bin:${PATH}

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["sleep", "infinity"]
