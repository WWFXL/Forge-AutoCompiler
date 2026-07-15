FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG APT_MIRROR=
ARG HTTP_PROXY=
ARG HTTPS_PROXY=

ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CC=gcc-13 \
    CXX=g++-13

RUN set -eux; \
    if [ -n "$APT_MIRROR" ]; then \
      sed -i \
        -e "s|http://archive.ubuntu.com/ubuntu|http://$APT_MIRROR/ubuntu|g" \
        -e "s|http://security.ubuntu.com/ubuntu|http://$APT_MIRROR/ubuntu|g" \
        /etc/apt/sources.list.d/ubuntu.sources; \
    fi; \
    if [ -n "$HTTP_PROXY" ]; then \
      printf 'Acquire::http::Proxy "%s";\n' "$HTTP_PROXY" > /etc/apt/apt.conf.d/90proxy; \
    fi; \
    if [ -n "$HTTPS_PROXY" ]; then \
      printf 'Acquire::https::Proxy "%s";\n' "$HTTPS_PROXY" >> /etc/apt/apt.conf.d/90proxy; \
    fi; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "120";\nAcquire::https::Timeout "120";\n' > /etc/apt/apt.conf.d/80-retries; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      autoconf \
      automake \
      bash \
      bison \
      build-essential \
      ca-certificates \
      ccache \
      cmake \
      curl \
      file \
      flex \
      g++-13 \
      gcc-13 \
      gdb \
      gettext \
      git \
      libbz2-dev \
      libcurl4-openssl-dev \
      libffi-dev \
      liblzma-dev \
      libncurses-dev \
      libreadline-dev \
      libsqlite3-dev \
      libssl-dev \
      libtool \
      libxml2-dev \
      libxslt1-dev \
      m4 \
      make \
      meson \
      ninja-build \
      patch \
      pkg-config \
      python3 \
      python3-pip \
      python3-venv \
      rsync \
      tar \
      unzip \
      uuid-dev \
      wget \
      xz-utils \
      zlib1g-dev; \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 130; \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 130; \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /workspace

CMD ["bash"]
