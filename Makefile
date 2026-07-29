.PHONY: help extract_translations compile_translations dummy_translations \
	build_dummy_translations detect_changed_source_translations \
	validate_translations check_translations_up_to_date

.DEFAULT_GOAL := help

WORKING_DIR := edx_sga
JS_TARGET := $(WORKING_DIR)/static/js/translations
EXTRACT_DIR := $(WORKING_DIR)/conf/locale/en/LC_MESSAGES
EXTRACTED_DJANGO_PARTIAL := $(EXTRACT_DIR)/django-partial.po
EXTRACTED_DJANGOJS_PARTIAL := $(EXTRACT_DIR)/djangojs-partial.po
EXTRACTED_DJANGO := $(EXTRACT_DIR)/django.po
EXTRACTED_DJANGOJS := $(EXTRACT_DIR)/djangojs.po

help: ## display this help message
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z_-]+:.*?## / {printf "\033[36m %-35s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

extract_translations: ## extract source strings to conf/locale
	cd $(WORKING_DIR) && i18n_tool extract
	if test -f $(EXTRACTED_DJANGO_PARTIAL); then mv $(EXTRACTED_DJANGO_PARTIAL) $(EXTRACTED_DJANGO); fi
	if test -f $(EXTRACTED_DJANGOJS_PARTIAL); then mv $(EXTRACTED_DJANGOJS_PARTIAL) $(EXTRACTED_DJANGOJS); fi

compile_translations: ## compile PO catalogues and the local JavaScript catalogues
	cd $(WORKING_DIR) && i18n_tool generate -v
	django-admin compilejsi18n --settings=edx_sga.test_settings --namespace StaffGradedAssignmentI18N --output $(JS_TARGET)

dummy_translations: ## generate fake-language translation catalogues
	cd $(WORKING_DIR) && i18n_tool dummy

build_dummy_translations: dummy_translations compile_translations ## generate and compile fake catalogues

detect_changed_source_translations: ## detect unextracted source strings
	cd $(WORKING_DIR) && i18n_tool changed

validate_translations: build_dummy_translations detect_changed_source_translations ## validate catalogues

check_translations_up_to_date: extract_translations compile_translations \
	dummy_translations detect_changed_source_translations ## regenerate and validate catalogues
