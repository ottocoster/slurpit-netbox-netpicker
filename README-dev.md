# githook
- `git config core.hooksPath .githooks` to auto increment the plugin version number

# docker
- `docker compose up -d --build`
- `docker compose -f tests/docker-compose.dev.yml run --rm test_container pytest --color=yes -v --durations 0 -rP`

# commands
- `python3 /opt/netbox/netbox/manage.py createsuperuser` create superuser
- `python3 /opt/netbox/netbox/manage.py makemigrations`