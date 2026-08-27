FROM alpine:3.19

# Install required tools
RUN apk add --no-cache \
    postgresql-client \
    redis \
    curl \
    bash \
    dcron \
    gzip \
    tar

# Copy backup scripts
COPY backup.sh /usr/local/bin/backup.sh
COPY restore.sh /usr/local/bin/restore.sh
COPY verify.sh /usr/local/bin/verify.sh
COPY cleanup.sh /usr/local/bin/cleanup.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/*.sh

# Create backup directory
RUN mkdir -p /backups

# Set up cron
RUN echo "0 2 * * * /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1" > /etc/crontabs/root
RUN echo "0 3 * * 0 /usr/local/bin/cleanup.sh >> /var/log/backup.log 2>&1" >> /etc/crontabs/root

WORKDIR /backups

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["crond", "-f", "-l", "2"]
