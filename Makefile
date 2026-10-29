# VentureOrder - Makefile per ambiente di sviluppo Odoo
#
# Target principali:
#   make up        - Avvia Odoo e PostgreSQL
#   make seed      - Popola il database con dati sintetici
#   make smoke     - Esegue il test di smoke
#   make reset     - Azzera il database e ripopola
#   make down      - Ferma i container
#   make logs      - Mostra i log di Odoo

.PHONY: help up down logs seed smoke reset clean datagen env-check wait-odoo

# Configurazione
COMPOSE := sudo docker compose
PYTHON := python3

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

env-check: ## Verifica che Docker sia disponibile
	@command -v docker >/dev/null 2>&1 || { \
		echo "$(RED)Errore: Docker non installato$(NC)"; \
		exit 1; \
	}
	@$(COMPOSE) version >/dev/null 2>&1 || { \
		echo "$(RED)Errore: Docker Compose non disponibile$(NC)"; \
		exit 1; \
	}
	@echo "$(GREEN)Docker OK$(NC)"

.env: ## Crea .env da .env.example se non esiste
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(YELLOW)Creato .env da .env.example$(NC)"; \
		echo "$(YELLOW)ATTENZIONE: Modificare le password prima dell'uso!$(NC)"; \
	fi

up: env-check .env ## Avvia Odoo e PostgreSQL
	@echo "$(GREEN)Avvio container...$(NC)"
	$(COMPOSE) up -d
	@echo ""
	@echo "$(GREEN)Container avviati!$(NC)"
	@echo "Odoo sarà disponibile su: http://localhost:8069"
	@echo ""
	@echo "$(YELLOW)Attendere 30-60 secondi per l'inizializzazione del database.$(NC)"
	@echo "Usare 'make logs' per monitorare il progresso."

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
	$(COMPOSE) up -d
	@echo "$(YELLOW)Attendo inizializzazione database (60s)...$(NC)"
	@sleep 60
	@$(MAKE) seed
	@$(MAKE) smoke

clean: down ## Rimuove tutto (container, volumi, immagini)
	@echo "$(RED)Rimozione completa...$(NC)"
	$(COMPOSE) down -v --rmi local
	@echo "$(GREEN)Pulizia completata$(NC)"

status: ## Mostra lo stato dei container
	$(COMPOSE) ps

shell-odoo: ## Apre una shell nel container Odoo
	$(COMPOSE) exec odoo bash

shell-db: ## Apre una shell psql nel database
	$(COMPOSE) exec db psql -U odoo -d vo_demo

# Target di sviluppo
test-connection: ## Testa la connessione XML-RPC a Odoo
	@$(PYTHON) -c "import xmlrpc.client; \
		c = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common'); \
		print('Odoo version:', c.version()['server_version'])"

# Target per CI
ci-test: up ## Test completo per CI (up, seed, smoke, down)
	@sleep 60
	@$(MAKE) seed
	@$(MAKE) smoke
	@$(MAKE) down
