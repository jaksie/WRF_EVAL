FROM dtcenter/metplus:6.2.1

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    lxml \
    plotly \
    kaleido \
    pandas \
    numpy \
    pyyaml \
    PyMySQL \
    mysql-connector-python \
    sqlalchemy \
    git+https://github.com/dtcenter/METdataio.git \
    git+https://github.com/dtcenter/METcalcpy.git \
    git+https://github.com/dtcenter/METplotpy.git

RUN mkdir -p /usr/local/lib/python3.14/site-packages/docs && \
    echo "3.2.0" > /usr/local/lib/python3.14/site-packages/docs/version