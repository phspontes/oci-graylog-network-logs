# OCI Graylog Network Logs

Stack Terraform para OCI Resource Manager que cria uma VM Oracle Linux 9, instala Graylog em Docker e automatiza a ingestao de logs de rede OCI arquivados no Object Storage.

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/phspontes/oci-graylog-network-logs/releases/latest/download/oci-graylog-network-logs.zip)

> O botao usa o asset `oci-graylog-network-logs.zip` da ultima release do GitHub. Depois de publicar uma nova versao da stack, gere o ZIP e publique uma release contendo esse arquivo.

## Isencao de responsabilidade

Antes de continuar tenha em mente que a utilizacao de qualquer script, codigo ou comandos contidos nesse repositorio e de sua total responsabilidade, nao cabendo aos autores dos codigos nenhum onus sobre qualquer utilizacao do conteudo aqui disponivel.

Teste adequadamente todo o conteudo em ambiente apropriado e integre os scripts de automacao a uma infraestrutura de monitoramento, para que seja possivel monitorar o funcionamento do processo de automacao e para mitigar possiveis falhas que podem ocorrer.

Este nao e um aplicativo oficial da Oracle e por isso, nao conta com o seu suporte. A Oracle nao se responsabiliza por nenhum conteudo aqui presente.

## O que a stack entrega

- VM Oracle Linux 9 em VCN/subnet existentes.
- VCN e subnet selecionaveis em compartments diferentes.
- Shape padrao `VM.Standard.E5.Flex`, 1 OCPU, 12 GB de RAM e disco de boot de 100 GB.
- IP privado opcional; se vazio, a OCI aloca automaticamente.
- NSG expondo apenas `22/tcp` para SSH e `9000/tcp` para a interface web do Graylog.
- Docker Engine, Graylog `7.1`, Graylog Data Node e MongoDB via Docker Compose.
- Data Node com certificado self-signed automatizado e heap calculado como metade da RAM da VM.
- Telemetria do Graylog desabilitada.
- Input GELF HTTP local em `127.0.0.1:12202`.
- Coletor Python via systemd lendo objetos de log no Object Storage com Instance Principal.
- Limite padrao de processamento para objetos modificados nos ultimos 7 dias, com `0` para sem limite.
- Content Pack com dashboards de VCN Flow Logs instalado automaticamente.

## Estrutura do repositorio

```text
oci-graylog-network-logs/
  main.tf
  variables.tf
  outputs.tf
  schema.yaml
  cloud-init.yaml.tftpl
  README.md
scripts/
  oci_object_storage_logs_to_graylog.py
  oci-vcn-flow-dashboard-final.json
  README-oci-object-storage-logs-to-graylog.md
```

## Pre-requisitos

- VCN e subnet existentes na OCI.
- Chave publica SSH.
- Bucket Object Storage recebendo logs pelo Service Connector Hub.
- Permissao para criar VM, VNIC, NSG e, opcionalmente, IAM Dynamic Group/Policy.
- Se `Criar Dynamic Group e Policy` ficar desabilitado, aplicar manualmente a policy gravada em `/root/graylog-oci-iam-policy.txt` na VM.

## Publicar no GitHub

Exemplo usando o repositorio `phspontes/oci-graylog-network-logs`:

```bash
git init
git add .
git commit -m "Initial OCI Graylog Network Logs stack"
git branch -M main
git remote add origin git@github.com:phspontes/oci-graylog-network-logs.git
git push -u origin main
```

## Deploy pelo botao

1. Publique este repositorio no GitHub.
2. Gere o pacote da stack:

```bash
cd oci-graylog-network-logs
zip -r ../oci-graylog-network-logs.zip .
```

3. Crie uma release no GitHub contendo o asset `oci-graylog-network-logs.zip`.
4. Use o botao **Deploy to Oracle Cloud** no topo deste README.
5. Preencha os parametros no Resource Manager e execute o job `Apply`.

Com GitHub CLI, a release pode ser criada assim:

```bash
gh release create v1.0.0 oci-graylog-network-logs.zip \
  --title "v1.0.0" \
  --notes "Initial release"
```

## Parametros principais

- `instance_compartment_ocid`: compartment onde a VM sera criada.
- `vcn_compartment_ocid`: compartment da VCN.
- `subnet_compartment_ocid`: compartment da subnet.
- `vcn_ocid` e `subnet_ocid`: rede onde a VM sera criada.
- `private_ip`: IP privado opcional da VM.
- `ssh_public_key`: chave publica SSH para o usuario `opc`.
- `ssh_source_cidr`: origem permitida para SSH.
- `graylog_source_cidr`: origem permitida para acesso web ao Graylog.
- `oci_log_bucket_compartment_ocid`: compartment do bucket de logs.
- `oci_log_bucket_name`: bucket com logs arquivados pelo Service Connector Hub.
- `oci_log_object_prefix`: prefixo opcional dos objetos no bucket.
- `oci_log_max_object_age_days`: processa somente objetos modificados nos ultimos N dias; `0` desativa o limite.
- `create_iam_policy`: cria Dynamic Group e Policy automaticamente se habilitado, restrita ao nome do bucket informado.

## Acesso apos o deploy

O output `graylog_url` mostra a URL HTTP do Graylog na porta `9000`.

Credenciais iniciais:

```text
Usuario: admin
Senha inicial: OCID da instancia
```

Na VM:

```bash
sudo cat /root/graylog-access.txt
```

Logs uteis:

```bash
sudo tail -f /var/log/cloud-init-output.log
cd /opt/graylog && sudo docker compose logs -f graylog
sudo journalctl -u oci-object-logs-to-graylog -f
```

## HTTPS

A stack publica o Graylog em HTTP na porta `9000/tcp`. Para HTTPS, use um OCI Load Balancer ou proxy reverso na frente do Graylog:

```text
Cliente -> HTTPS 443 -> Load Balancer/Nginx -> HTTP 9000 -> Graylog
```

## Arquivos externos baixados pela VM

Por padrao, o cloud-init baixa estes arquivos deste mesmo repositorio:

```text
https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci_object_storage_logs_to_graylog.py
https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci-vcn-flow-dashboard-final.json
```

Essas URLs podem ser sobrescritas no schema do Resource Manager se necessario.
