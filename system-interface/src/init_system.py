#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Inicialização do Sistema
Cria banco de dados e admin padrão
"""

import sys
import os
import getpass

# Adiciona o diretório atual ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import Database

def init_system():
    """Inicializa o sistema com banco de dados e admin"""
    
    print("=" * 70)
    print("INICIALIZAÇÃO DO SISTEMA DE CADASTRO DE USUÁRIOS")
    print("=" * 70)
    print()
    
    # Caminho do banco (na raiz do projeto, não na pasta src)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assistant.db')
    
    # Verificar se já existe
    if os.path.exists(db_path):
        print(f"⚠️  Banco de dados já existe: {db_path}")
        print()
        resposta = input("Deseja APAGAR e criar um novo? (s/N): ").strip().lower()
        if resposta != 's':
            print("Operação cancelada.")
            return False
        
        # Remove banco antigo
        os.remove(db_path)
        print("✓ Banco antigo removido.")
        print()
    
    # Cria novo banco
    print("Criando novo banco de dados...")
    db = Database(db_path)
    print("✓ Banco de dados criado com sucesso!")
    print()
    
    # Verifica se já tem admin
    if db.has_any_admin():
        print("✓ Já existe um administrador configurado.")
        db.close()
        return True
    
    # Cria admin padrão
    print("Nenhum administrador encontrado.")
    print()
    print("Vamos criar o primeiro administrador:")
    print("-" * 70)
    
    while True:
        username = input("Nome de usuário (admin): ").strip()
        if not username:
            username = "admin"
        
        if len(username) < 3:
            print("⚠️  O nome deve ter pelo menos 3 caracteres.")
            continue
        
        break
    
    print()
    
    while True:
        password = getpass.getpass("Senha (mínimo 6 caracteres): ")
        
        if len(password) < 6:
            print("⚠️  A senha deve ter pelo menos 6 caracteres.")
            continue
        
        password_confirm = getpass.getpass("Confirme a senha: ")
        
        if password != password_confirm:
            print("⚠️  As senhas não coincidem. Tente novamente.")
            print()
            continue
        
        break
    
    print()
    print("Criando administrador...")
    db.upsert_admin(username, password)
    print("✓ Administrador criado com sucesso!")
    print()
    
    db.close()
    
    print("-" * 70)
    print("✓ SISTEMA INICIALIZADO COM SUCESSO!")
    print()
    print(f"  Usuário: {username}")
    print(f"  Banco de dados: {db_path}")
    print()
    print("Para iniciar o servidor web, execute:")
    print("  python3 app.py")
    print()
    print("ou")
    print()
    print("  ./start.sh")
    print("=" * 70)
    
    return True


if __name__ == '__main__':
    try:
        if init_system():
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("Operação cancelada pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"✗ Erro: {e}")
        sys.exit(1)
