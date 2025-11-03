FROM kbase/sdkpython:3.8.10
LABEL maintainer="ac.shahnam"

USER root

# fetch tools to install micromamba
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl bzip2 ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# micromamba
ENV MAMBA_ROOT_PREFIX=/opt/conda
ADD https://micro.mamba.pm/api/micromamba/linux-64/latest /tmp/micromamba.tar.bz2
RUN tar -xvjf /tmp/micromamba.tar.bz2 -C /usr/local/bin/ --strip-components=1 bin/micromamba && \
    chmod +x /usr/local/bin/micromamba && rm -f /tmp/micromamba.tar.bz2

# create env
COPY env-grin.yml /tmp/env-grin.yml
RUN /usr/local/bin/micromamba create -y -f /tmp/env-grin.yml && \
    /usr/local/bin/micromamba clean -a -y

# allow non-root to read/execute env; chown only if kbmodule exists
RUN chmod -R a+rX /opt/conda && \
    if id -u kbmodule >/dev/null 2>&1; then \
      chown -R kbmodule:kbmodule /opt/conda; \
    else \
      echo "kbmodule user not present at build time; skipping chown"; \
    fi

# GRIN code + R deps (inside the grin env)
RUN /usr/local/bin/micromamba run -n grin bash -lc '\
  git lfs install && \
  git clone https://github.com/sullivanka/GRIN /opt/GRIN --depth 1 \
'


RUN /usr/local/bin/micromamba run -n grin Rscript -e "install.packages('remotes', repos='https://cloud.r-project.org'); \
    remotes::install_github('alberto-valdeolivas/RandomWalkRestartMH'); \
    remotes::install_github('agentlans/KneeArrower')"


# module files
COPY . /kb/module
WORKDIR /kb/module
RUN make

# base image typically switches to kbmodule; if not, you can uncomment:
# RUN useradd -m -s /bin/bash kbmodule || true
# USER kbmodule
