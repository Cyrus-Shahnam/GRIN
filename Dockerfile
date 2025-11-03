FROM kbase/sdkpython:3.8.10
LABEL maintainer="ac.shahnam"

USER root

# --- tools to fetch & unpack micromamba ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl bzip2 ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# --- micromamba (single static binary) ---
ENV MAMBA_ROOT_PREFIX=/opt/conda
ADD https://micro.mamba.pm/api/micromamba/linux-64/latest /tmp/micromamba.tar.bz2
RUN tar -xvjf /tmp/micromamba.tar.bz2 -C /usr/local/bin/ --strip-components=1 bin/micromamba && \
    chmod +x /usr/local/bin/micromamba && rm -f /tmp/micromamba.tar.bz2

RUN pwd

# --- create the R env (prebuilt R pkgs from conda; avoids compiling igraph) ---
COPY env-grin.yml /tmp/env-grin.yml
RUN /usr/local/bin/micromamba create -y -f /tmp/env-grin.yml && \
    /usr/local/bin/micromamba clean -a -y

# --- allow non-root user to read/execute the env; chown only if kbmodule exists ---
RUN chmod -R a+rX /opt/conda && \
    if id -u kbmodule >/dev/null 2>&1; then \
      chown -R kbmodule:kbmodule /opt/conda; \
    else \
      echo "kbmodule user not present at build time; skipping chown"; \
    fi

# --- GRIN source and R deps (all inside env 'grin') ---

# Clone GRIN; skip LFS smudge on clone to avoid checkout failures
RUN /usr/local/bin/micromamba run -n grin bash -lc '\
  git lfs install && \
  GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/sullivanka/GRIN /opt/GRIN --depth 1 \
'

# Ensure r-igraph is present from conda (binary, no CRAN compile)
RUN /usr/local/bin/micromamba install -y -n grin -c conda-forge r-igraph

# Install dnet (conda -> Bioconductor -> CRAN fallback)
RUN /usr/local/bin/micromamba install -y -n grin -c conda-forge -c bioconda r-dnet || \
    /usr/local/bin/micromamba install -y -n grin -c conda-forge -c bioconda bioconductor-dnet || \
    /usr/local/bin/micromamba run -n grin Rscript -e "install.packages('BiocManager', repos='https://cloud.r-project.org'); BiocManager::install('dnet', ask=FALSE)"

# Install GitHub-only R deps but DO NOT upgrade conda-installed deps
RUN /usr/local/bin/micromamba run -n grin Rscript -e "\
  options(repos='https://cloud.r-project.org'); \
  Sys.setenv(R_REMOTES_UPGRADE='never', R_REMOTES_NO_ERRORS_FROM_WARNINGS='true'); \
  install.packages('remotes'); \
  remotes::install_github('alberto-valdeolivas/RandomWalkRestartMH', dependencies=FALSE, upgrade='never'); \
  remotes::install_github('agentlans/KneeArrower', dependencies=FALSE, upgrade='never') \
"

# --- module files & compile ---
COPY . /kb/module
WORKDIR /kb/module
RUN make
