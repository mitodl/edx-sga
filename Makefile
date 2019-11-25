
extract_translations: ## creates the django.po and djangojs.po files.
	django-admin.py makemessages -l en -v0 --ignore="*/management/*" --ignore="*/css/*" -d django
	django-admin.py makemessages -l en -v0 --ignore="*/management/*" --ignore="*/css/*" -d djangojs -e js,jsx

pull_translations: ## pull translations from Transifex
	tx pull -af --mode reviewed --minimum-perc=1

push_translations: ## push source translation files (.po) to Transifex
	tx push -s

compile_translations: ## compiles the *.po & *.mo files
	i18n_tool generate -v

generate_dummy_translations: ## generate dummy translations
	i18n_tool dummy

validate_translations: ## Test translation files
	i18n_tool validate -v
