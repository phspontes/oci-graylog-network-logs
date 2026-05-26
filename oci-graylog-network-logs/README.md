# OCI Graylog Network Logs

Esta stack do OCI Resource Manager cria uma VM Oracle Linux 9 em uma VCN/subnet existentes e instala Graylog em Docker via cloud-init para analise de logs de rede OCI.

## Isencao de responsabilidade

Antes de continuar tenha em mente que a utilizacao de qualquer script, codigo ou comandos contidos nesse repositorio e de sua total responsabilidade, nao cabendo aos autores dos codigos nenhum onus sobre qualquer utilizacao do conteudo aqui disponivel.

Teste adequadamente todo o conteudo em ambiente apropriado e integre os scripts de automacao a uma infraestrutura de monitoramento, para que seja possivel monitorar o funcionamento do processo de automacao e para mitigar possiveis falhas que podem ocorrer.

Este nao e um aplicativo oficial da Oracle e por isso, nao conta com o seu suporte. A Oracle nao se responsabiliza por nenhum conteudo aqui presente.

## O que a stack provisiona

- 1 VM Oracle Linux 9 no compartment selecionado para a instancia.
- VCN e subnet podem ser selecionadas em compartments diferentes.
- IP privado da VM pode ser informado manualmente; se ficar vazio, a OCI aloca automaticamente.
- 1 Network Security Group criado no compartment da VCN, expondo somente SSH `22/tcp` e Graylog Web `9000/tcp`.
- Docker Engine.
- Graylog `7.1`, Graylog Data Node e MongoDB via Docker Compose.
- Setup automatico do Data Node com `GRAYLOG_SELFSIGNED_STARTUP=true`.
- Heap do Data Node calculado como metade da RAM da VM, limitado a `31g`.
- Telemetria do Graylog desabilitada por padrao.
- Input GELF HTTP local criado automaticamente na porta `12202/tcp`, publicado apenas em `127.0.0.1`.
- Content Pack de dashboards VCN Flow Logs baixado e instalado automaticamente no primeiro start do Graylog.
- Coletor Python via systemd lendo logs do Object Storage e enviando para o Graylog.
- Processamento limitado por padrao a objetos modificados nos ultimos 7 dias; use `0` para sem limite.

## Acesso

Depois que o job do Resource Manager terminar, aguarde alguns minutos para o cloud-init baixar as imagens e iniciar os containers.

- URL: output `graylog_url`
- Usuario: `admin`
- Senha inicial: OCID da instancia, exibido no output `instance_id`

Na VM, o mesmo resumo fica em:

```bash
sudo cat /root/graylog-access.txt
```

Logs do bootstrap:

Se a instalacao de pacotes encontrar lock temporario de RPM/DNF, o script tenta novamente automaticamente antes de falhar.


```bash
sudo tail -f /var/log/cloud-init-output.log
```

Logs do Graylog:

```bash
cd /opt/graylog
sudo docker compose logs -f graylog
```

## Empacotar para o Resource Manager

Crie um ZIP com o conteudo desta pasta:

```bash
cd oci-graylog-network-logs
zip -r ../oci-graylog-network-logs.zip .
```

Depois crie uma stack no OCI Resource Manager usando esse ZIP.

## HTTPS

Esta stack publica o Graylog em HTTP na porta `9000/tcp`.

Para HTTPS, o caminho recomendado em OCI e colocar um OCI Load Balancer ou Nginx na frente:

```text
Cliente -> HTTPS 443 -> Load Balancer/Nginx -> HTTP 9000 -> Graylog
```



## Content Pack Graylog

A variavel `graylog_content_pack_url` aponta por padrao para:

```text
https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci-vcn-flow-dashboard-final.json
```

Durante o cloud-init, o JSON e baixado para `/opt/graylog/contentpacks/`, validado e configurado para auto-instalacao pelo loader nativo do Graylog no primeiro start.

## OCI Object Storage Logs

Informe no Resource Manager:

- `Bucket de logs OCI`: bucket onde o Service Connector Hub grava os logs.
- `Prefixo dos objetos de log`: prefixo opcional, por exemplo `oci-logs/`.
- `Dias maximos de historico dos logs`: default `7`; use `0` para processar objetos sem limite por idade.

A VM usa Instance Principal para ler o bucket. Crie um Dynamic Group para a instancia e policies como:

```text
Allow dynamic-group <dynamic-group-graylog> to inspect buckets in compartment <compartment-do-bucket> where target.bucket.name = '<nome-do-bucket>'
Allow dynamic-group <dynamic-group-graylog> to read objects in compartment <compartment-do-bucket> where target.bucket.name = '<nome-do-bucket>'
```

O servico local do coletor e:

```bash
sudo systemctl status oci-object-logs-to-graylog
sudo journalctl -u oci-object-logs-to-graylog -f
```

A porta GELF HTTP `12202/tcp` nao fica exposta externamente; ela e publicada apenas em `127.0.0.1` para uso pelo coletor local.

## IAM Opcional

A stack tem a opcao `Criar Dynamic Group e Policy`.

- `false` por padrao: nao cria IAM; a VM grava a sintaxe em `/root/graylog-oci-iam-policy.txt`.
- `true`: cria um Dynamic Group restrito ao OCID da instancia e uma Policy no compartment do bucket, limitada ao nome do bucket informado, para permitir leitura dos objetos.

Para o modo automatico funcionar, o Resource Manager precisa ter permissao para criar Dynamic Groups e Policies. Se a organizacao centraliza IAM, mantenha `false` e entregue o arquivo de sintaxe gerado na VM para aplicacao manual.
