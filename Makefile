# VentureOrder - Makefile per ambiente di sviluppo Odoo
#
# Target principali:
#   make conf      - Genera config/odoo.conf dal template
#   make init      - Inizializza il database (una sola volta)
#   make up        - Avvia Odoo e PostgreSQL
#   make seed      - Popola il database con dati sintetici
#   make smoke     - Esegue il test di smoke
#   make reset     - Azzera il database e ripopola
#   make down      - Ferma i container
#   make logs      - Mostra i log di Odoo
#
# Per VM con problemi di rete Docker:
#   make up VM=1   - Usa network_mode: host

.PHONY: help conf up down logs seed smoke reset clean datagen env-check wait-odoo init test lint ui eval

EVAL_SEED ?= 42
EVAL_MODEL ?= qwen2.5:3b-instruct
EVAL_SAMPLE ?= 50
EVAL_BEFORE_COMMIT ?= aea6f9b

# Non usare `-include .env` + `export`: Make interpreta `$` e `#` e corrompe le password.
# scripts/generate_odoo_conf.py (e seed/smoke) leggono `.env` da sé.
PYTHON := python3
POSTGRES_USER := $(shell $(PYTHON) scripts/generate_odoo_conf.py --get POSTGRES_USER)
POSTGRES_DB := $(shell $(PYTHON) scripts/generate_odoo_conf.py --get POSTGRES_DB)

# Compose command - usa VM=1 per network_mode: host
ifeq ($(VM),1)
COMPOSE := docker compose -f docker-compose.yml -f docker-compose.vm.yml
DB_HOST := localhost
else
COMPOSE := docker compose
DB_HOST := db
endif

# Colori per output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

help: ## Mostra questo help
	@echo "VentureOrder - Comandi disponibili:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "Per VM con problemi di rete Docker: make up VM=1"

env-check: ## Verifica che Docker sia disponibile e .env esista
	@command -v docker >/dev/null 2>&1 || { \
		echo "$(RED)Errore: Docker non installato$(NC)"; \
		exit 1; \
	}
	@docker compose version >/dev/null 2>&1 || { \
		echo "$(RED)Errore: Docker Compose non disponibile$(NC)"; \
		exit 1; \
	}
	@if [ ! -f .env ]; then \
		echo "$(RED)Errore: File .env non trovato$(NC)"; \
		echo "Esegui: cp .env.example .env && nano .env"; \
		exit 1; \
	fi
	@$(PYTHON) scripts/generate_odoo_conf.py --check
	@echo "$(GREEN)Ambiente OK$(NC)"

conf: env-check ## Genera config/odoo.conf dal template
	@echo "$(GREEN)Generazione config/odoo.conf...$(NC)"
	@DB_HOST=$(DB_HOST) $(PYTHON) scripts/generate_odoo_conf.py

init: conf ## Inizializza il database con i moduli (una sola volta)
	@echo "$(GREEN)Inizializzazione database...$(NC)"
	$(COMPOSE) up -d db
	@echo "$(YELLOW)Attendo che PostgreSQL sia pronto...$(NC)"
	@for i in $$(seq 1 30); do \
		if $(COMPOSE) exec -T db pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB) -h localhost >/dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@echo "$(GREEN)Inizializzazione moduli Odoo...$(NC)"
	$(COMPOSE) run --rm odoo \
		--config=/etc/odoo/odoo.conf \
		--db_host=$(DB_HOST) \
		--init=sale_management,stock,contacts,product \
		--without-demo=all \
		--stop-after-init
	@echo "$(GREEN)Inizializzazione completata!$(NC)"

up: conf ## Avvia Odoo e PostgreSQL
	@echo "$(GREEN)Avvio container...$(NC)"
	$(COMPOSE) up -d
	@echo ""
	@echo "$(GREEN)Container avviati!$(NC)"
ifeq ($(VM),1)
	@echo "Odoo disponibile su: http://localhost:8069"
else
	@echo "Odoo disponibile su: http://127.0.0.1:8069"
endif
	@echo ""
	@echo "$(YELLOW)Se è la prima esecuzione, esegui: make init$(NC)"

wait-odoo: ## Attende che Odoo sia pronto
	@echo "$(YELLOW)Attendo che Odoo sia pronto...$(NC)"
	@for i in $$(seq 1 60); do \
		if curl -s http://localhost:8069/web/database/selector >/dev/null 2>&1; then \
			echo "$(GREEN)Odoo pronto!$(NC)"; \
			exit 0; \
		fi; \
		echo "  Tentativo $$i/60..."; \
		sleep 2; \
	done; \
	echo "$(RED)Timeout: Odoo non risponde$(NC)"; \
	exit 1

down: ## Ferma i container
	@echo "$(YELLOW)Arresto container...$(NC)"
	$(COMPOSE) down
	@echo "$(GREEN)Container fermati$(NC)"

logs: ## Mostra i log di Odoo (Ctrl+C per uscire)
	$(COMPOSE) logs -f odoo

logs-all: ## Mostra tutti i log (Odoo + PostgreSQL)
	$(COMPOSE) logs -f

datagen: ## Genera i dati master sintetici
	@echo "$(GREEN)Generazione dati master...$(NC)"
	$(PYTHON) datagen/generate_master_data.py
	@echo "$(GREEN)Dati generati in datagen/master/$(NC)"

seed: datagen wait-odoo ## Popola Odoo con dati sintetici
	@echo "$(GREEN)Seed del database Odoo...$(NC)"
	$(PYTHON) scripts/seed_odoo.py
	@echo "$(GREEN)Seed completato!$(NC)"

smoke: ## Esegue il test di smoke
	@echo "$(GREEN)Esecuzione smoke test...$(NC)"
	$(PYTHON) scripts/smoke_test.py

reset: down ## Azzera il database e ripopola
	@echo "$(YELLOW)Rimozione volumi...$(NC)"
	$(COMPOSE) down -v
	@echo "$(GREEN)Riavvio con database pulito...$(NC)"
	@$(MAKE) init VM=$(VM)
	@$(MAKE) up VM=$(VM)
	@$(MAKE) wait-odoo
	@$(MAKE) seed
	@$(MAKE) smoke

clean: down ## Rimuove tutto (container, volumi, immagini)
	@echo "$(RED)Rimozione completa...$(NC)"
	$(COMPOSE) down -v --rmi local
	@rm -f config/odoo.conf
	@echo "$(GREEN)Pulizia completata$(NC)"

status: ## Mostra lo stato dei container
	$(COMPOSE) ps

shell-odoo: ## Apre una shell nel container Odoo
	$(COMPOSE) exec odoo bash

shell-db: ## Apre una shell psql nel database
	$(COMPOSE) exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# Target di sviluppo
test-connection: ## Testa la connessione XML-RPC a Odoo
	@$(PYTHON) -c "import xmlrpc.client; \
		c = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common'); \
		print('Odoo version:', c.version()['server_version'])"

# Test e linting
lint: ## Esegue ruff su tutto il repo
	ruff check .

test: ## Esegue i test unitari
	pytest tests -q

ui: ## Avvia la console di revisione (FastAPI + Jinja2)
	uvicorn ventureorder.web.app:create_app --factory --host 127.0.0.1 --port 8000

eval: ## Valutazione extract riproducibile (Ollama, seed/modello/parametri fissi)
	PYTHONPATH=. $(PYTHON) -m extract.eval_run \
		--seed $(EVAL_SEED) \
		--model $(EVAL_MODEL) \
		--sample $(EVAL_SAMPLE) \
		--before-commit $(EVAL_BEFORE_COMMIT) \
		--exclude-pdf \
		--also-no-llm \
		--output-dir docs/eval
