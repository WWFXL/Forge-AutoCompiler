FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG APT_MIRROR=mirrors.ustc.edu.cn
ARG HTTP_PROXY=
ARG HTTPS_PROXY=

ENV TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CC=gcc-13 \
    CXX=g++-13

COPY ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources

RUN set -eux; \
    sed -i "s|mirrors.ustc.edu.cn|${APT_MIRROR}|g" /etc/apt/sources.list.d/ubuntu.sources; \
    if [ -n "$HTTP_PROXY" ]; then \
      printf 'Acquire::http::Proxy "%s";\n' "$HTTP_PROXY" > /etc/apt/apt.conf.d/90proxy; \
    fi; \
    if [ -n "$HTTPS_PROXY" ]; then \
      printf 'Acquire::https::Proxy "%s";\n' "$HTTPS_PROXY" >> /etc/apt/apt.conf.d/90proxy; \
    fi; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "120";\nAcquire::https::Timeout "120";\n' > /etc/apt/apt.conf.d/80-retries; \
    # Ubuntu 最小镜像缺少 CA：仅引导签名校验的证书包，随后恢复 HTTPS。
    if [ ! -s /etc/ssl/certs/ca-certificates.crt ]; then \
      sed -i 's|https://|http://|g' /etc/apt/sources.list.d/ubuntu.sources; \
      apt-get update --error-on=any; \
      apt-get install -y --no-install-recommends ca-certificates; \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources; \
    fi; \
    apt-get update --error-on=any; \
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
