FROM forge-rtorrent-reference-base:581-d27a6ab733c7
RUN apt-get -o Acquire::Retries=0 update && apt-get -o Acquire::Retries=0 install -y --no-install-recommends autoconf-archive libcppunit-dev libtool-bin
RUN mkdir -p /opt/forge-environment && dpkg-query -W > /opt/forge-environment/packages.tsv && sha256sum /var/lib/dpkg/status > /opt/forge-environment/dpkg-status.sha256
