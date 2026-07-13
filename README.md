# Homelab Toolkit

Toolkit pessoal para backup, diagnostico e recuperacao de um homelab Proxmox.

O objetivo e permitir instalar um Proxmox novo, instalar o Toolkit, montar o storage de backups e recuperar o homelab com o minimo de trabalho manual.

## Instalar num Proxmox

```bash
apt update
apt install -y git
cd /opt
git clone https://github.com/alexkiddddd/Homelab-Toolkit.git homelab-src
cd homelab-src
./install
```

Confirmar:

```bash
homelab version
homelab doctor
```

## Atualizar

Depois da primeira instalacao por Git, basta:

```bash
homelab update
homelab version
homelab doctor
```

O comando `homelab version` mostra a versao base e o commit instalado, por exemplo:

```text
0.1.0 (db10c17)
```

## Criar backup

Na maquina atual:

```bash
homelab backup
```

Por defeito, os snapshots do host ficam em:

```text
/mnt/pve/backups/host-config
```

Os backups LXC do Proxmox ficam normalmente em:

```text
/mnt/pve/backups/dump
```

## Recuperar ou migrar maquina

Na maquina antiga:

```bash
homelab backup
```

Na maquina nova:

1. Instalar Proxmox.
2. Garantir rede basica e acesso por consola, SSH ou Web UI.
3. Montar ou disponibilizar temporariamente o storage com os backups.
4. Instalar o Toolkit via Git.
5. Executar:

```bash
homelab restore
```

### Bootstrap da storage de backups

O Toolkit precisa de conseguir ler os backups antes de restaurar o host.

Isto significa que, numa maquina nova, a NAS/storage onde vivem os backups tem de estar acessivel antes de executar `homelab restore`.

Exemplo do fluxo esperado:

```text
Proxmox novo
-> rede basica
-> NAS/storage de backups acessivel
-> instalar Toolkit
-> homelab restore
```

O restore consegue depois repor a configuracao permanente das storages Proxmox a partir do snapshot, incluindo `/etc/pve/storage.cfg`. Mas para descobrir e ler esse snapshot, precisa primeiro de acesso inicial ao local dos backups.

Se `homelab restore` nao encontrar snapshots de host, o modo guiado mostra este passo de bootstrap e exemplos de montagem NFS/SMB antes de continuar.

Por defeito, o Toolkit procura:

```text
/mnt/pve/backups/host-config
/mnt/pve/backups/dump
```

O modo guiado faz:

1. Pre-verificacao dos backups.
2. Restore Host.
3. Restore LXC.
4. Doctor final.

## Restore Host

Tambem pode ser executado diretamente:

```bash
homelab restore-host
```

Depois da analise do snapshot, e possivel restaurar um ou varios componentes:

```text
2,5,6,7,8,10,3
```

Ordem recomendada:

```text
Config Homelab -> Storages -> Rede -> Tailscale -> LCDproc -> Fan Control -> Jobs de Backup
```

Tambem existe:

```text
all
```

para os componentes recomendados, e:

```text
9
```

para restaurar servicos systemd de forma seletiva.

O componente `10` restaura o Fan Control do Sophos XG210:

- `/etc/systemd/system/xg210-fan.service`
- `/usr/local/bin/xg210-fan.sh`

Depois de restaurar, o Toolkit faz `systemctl daemon-reload`, pode reativar o servico e pode reinicia-lo mediante confirmacao.

## Comandos principais

```bash
homelab backup        # Backup da configuracao do host
homelab restore       # Assistente de recuperacao
homelab restore-host  # Analise/restauro do host
homelab restore-lxc   # Restauro de containers LXC
homelab doctor        # Diagnostico do host
homelab update        # Atualizar Toolkit a partir do Git
homelab version       # Mostrar versao e commit instalado
```

## Seguranca

Este repositorio deve conter apenas o Toolkit.

Nao guardar aqui:

- snapshots ou backups reais;
- tokens;
- passwords;
- chaves privadas;
- ficheiros `.env`;
- configuracoes com segredos;
- dumps de `/etc`, `/root` ou `/etc/pve`.

Antes de publicar ou fazer push, e boa pratica verificar:

```bash
git status
git grep -n -i "password\|token\|secret\|privkey\|authkey\|smtp"
```
