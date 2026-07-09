# Homelab Toolkit

Toolkit pessoal para backup, diagnostico e recuperacao de um homelab Proxmox.

## Instalar num Proxmox novo

```bash
apt update
apt install -y git
git clone https://github.com/TEU-USER/Homelab-Toolkit.git
cd Homelab-Toolkit
chmod +x install
./install
```

Depois:

```bash
homelab version
homelab doctor
homelab restore
```

## Migrar ou recuperar maquina

Na maquina antiga:

```bash
homelab backup
```

Na maquina nova:

1. Instalar Proxmox.
2. Montar ou disponibilizar o storage com os backups.
3. Instalar este Toolkit.
4. Executar `homelab restore`.

## Nota de seguranca

Este repositorio deve conter apenas o Toolkit.
Nao guardar aqui snapshots, backups, tokens, passwords, chaves privadas ou configuracoes com segredos.
