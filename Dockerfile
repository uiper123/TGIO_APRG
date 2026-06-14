# remote-ssh-desktop server Docker image
# Usage:
#   docker run -p 2222:22 -e SSH_PASSWORD=secret ghcr.io/uiper123/tgio-aprg-server
#
# Connect from the client: host=localhost port=2222
FROM debian:bookworm-slim

ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server xvfb xauth xclip xterm \
    libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libegl1 libgl1 \
    libxcb-xinput0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
    libx11-6 libxext6 libxtst6 libxfixes3 libxdamage1 \
    && rm -rf /var/lib/apt/lists/*

# Create ssh user and configure SSH
RUN useradd -ms /bin/bash rsduser && \
    echo "rsduser:${SSH_PASSWORD:-changeme}" | chpasswd && \
    mkdir -p /run/sshd /home/rsduser/.ssh && \
    chmod 700 /home/rsduser/.ssh && \
    ssh-keygen -A

# Allow SSH login and configure remote command
RUN echo "AllowUsers rsduser" >> /etc/ssh/sshd_config && \
    echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config && \
    echo "X11Forwarding no" >> /etc/ssh/sshd_config && \
    echo "AcceptEnv REMOTE_SSH_DESKTOP_SESSION" >> /etc/ssh/sshd_config

# Copy the server binary (injected at build time by CI)
# In development you can also mount the binary:
#   docker run -v ./dist/remote-ssh-desktop-server:/usr/local/bin/remote-ssh-desktop-server ...
COPY dist/remote-ssh-desktop-server /usr/local/bin/remote-ssh-desktop-server
RUN chmod +x /usr/local/bin/remote-ssh-desktop-server

# Expose SSH port
EXPOSE 22

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD remote-ssh-desktop-server --version || exit 1

ENTRYPOINT ["/usr/sbin/sshd", "-D"]
