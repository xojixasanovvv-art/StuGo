# Django loyihasi uchun qulay buyruqlar.
#
# Muhim: venv ichidagi python/daphne ni TO'G'RI ishlatadi (PATH ga bog'liq emas),
# shuning uchun `make run` faqat `.venv` ni oldindan faollashtirsa bo'ladi.
VENV ?= .venv
PY ?= $(VENV)/bin/python
DAPHNE ?= $(VENV)/bin/daphne
PIP ?= $(VENV)/bin/pip

# Django shell: make dj
dj:
	$(PY) manage.py shell

# Serverni ishga tushirish: make run
# Muhim: runserver WSGI server — WebSocket (chat real-time) ishlamaydi,
# shuning uchun Daphne (ASGI) ishlatiladi.
# Boshqa port: make run PORT=9000
run:
	$(DAPHNE) -b 127.0.0.1 -p $(or $(PORT),8000) config.asgi:application

# Barcha qurilmalardan (telefon, boshqa kompyuter) kirish: make run_lan
# Muhim: ALLOWED_HOSTS ga 0.0.0.0 .env da bo'lishi SHART, aks holda
# DisallowedHost xatosi chiqadi.
run_lan:
	$(DAPHNE) -b 0.0.0.0 -p $(or $(PORT),8000) config.asgi:application

# Migratsiya yaratish va qo'llash: make mig
mig:
	$(PY) manage.py makemigrations
	$(PY) manage.py migrate

# Testlar: make test
test:
	$(PY) manage.py test apps

# Testlar (teskarari tartibda): make test-reverse
test-reverse:
	$(PY) manage.py test apps --reverse

# Superuser yaratish: make superuser
superuser:
	$(PY) manage.py createsuperuser

# Yangi app yaratish: make app APP=nomi
app:
	$(PY) manage.py startapp apps

# Paketlarni o'rnatish: make install
install:
	$(PIP) install -r requirements.txt

# Staticallyk fayllarni yig'ish: make collect
collect:
	$(PY) manage.py collectstatic --noinput