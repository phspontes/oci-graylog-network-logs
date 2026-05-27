# OCI Graylog Network Logs

Esta stack do OCI Resource Manager cria uma VM Oracle Linux 9 em uma VCN/subnet existente e instala o Graylog em Docker via cloud-init para análise de logs de rede da OCI.

## Isenção de responsabilidade

Antes de continuar, tenha em mente que a utilização de qualquer script, código ou comando contido neste repositório é de sua total responsabilidade, não cabendo aos autores dos códigos nenhum ônus sobre qualquer utilização do conteúdo aqui disponível.

Teste adequadamente todo o conteúdo em ambiente apropriado e integre os scripts de automação a uma infraestrutura de monitoramento, para que seja possível acompanhar o funcionamento do processo de automação e mitigar possíveis falhas.

Este não é um aplicativo oficial da Oracle e, por isso, não conta com o seu suporte. A Oracle não se responsabiliza por nenhum conteúdo aqui presente.

## O que a stack provisiona

- 1 VM Oracle Linux 9 no compartment selecionado para a instância.
- VCN e subnet podem ser selecionadas em compartments diferentes.
- IP privado da VM pode ser informado manualmente; se ficar vazio, a OCI aloca automaticamente.
- 1 Network Security Group no compartment da VCN, expondo somente SSH `22/tcp` e Graylog Web `9000/tcp`.
- Docker Engine.
- Graylog `7.1`, Graylog Data Node e MongoDB via Docker Compose.
- Setup automático do Data Node com `GRAYLOG_SELFSIGNED_STARTUP=true`.
- Heap do Data Node calculado como metade da RAM da VM, limitado a `31g`.
- Telemetria do Graylog desabilitada.
- Input GELF HTTP local criado automaticamente na porta `12202/tcp`, publicado apenas em `127.0.0.1`.
- Content Pack de dashboards VCN Flow Logs baixado e instalado automaticamente no primeiro start do Graylog.
- Coletor Python via systemd lendo logs do Object Storage e enviando para o Graylog.
- Processamento limitado, por padrão, a objetos modificados nos últimos 7 dias. Use `0` para não limitar por idade.

## Configurações manuais necessárias

Antes de executar a stack, você deve criar e configurar manualmente na OCI:

- o bucket Object Storage que receberá os logs;
- a habilitação dos VCN Flow Logs nos recursos de rede desejados;
- o Service Connector Hub enviando os logs do OCI Logging para o bucket;
- as regras de rota e segurança necessárias para a VM acessar internet/serviços OCI;
- as permissões IAM para leitura do bucket, caso não use a opção automática de Dynamic Group e Policy da stack.

A stack parte do pressuposto de que os logs já estão sendo gravados no bucket informado. Ela provisiona o Graylog, o coletor e os dashboards, mas não cria o pipeline de geração/exportação dos VCN Flow Logs.

## Como usar

1. Crie manualmente o bucket, habilite os VCN Flow Logs e configure o Service Connector Hub para gravar os logs no bucket.
2. Crie a stack no OCI Resource Manager usando o ZIP deste diretório.
3. Preencha os parâmetros de rede, instância, bucket de logs e acesso.
4. Execute o job **Apply**.
5. Aguarde o cloud-init concluir a instalação.
6. Acesse o Graylog usando o output `graylog_url`.

## Acesso

Depois que o job do Resource Manager terminar, aguarde alguns minutos para o cloud-init baixar as imagens e iniciar os containers.

- URL: output `graylog_url`
- Usuário: `admin`
- Senha inicial: OCID da instância, exibido no output `instance_id`

Na VM, o mesmo resumo fica em:

```bash
sudo cat /root/graylog-access.txt
```

Logs do bootstrap:

```bash
sudo tail -f /var/log/cloud-init-output.log
sudo cloud-init status --long
```

Logs do Graylog:

```bash
cd /opt/graylog
sudo docker compose logs -f graylog
```

## Content Pack Graylog

A variável `graylog_content_pack_url` aponta, por padrão, para:

```text
https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci-vcn-flow-dashboard-final.json
```

Durante o cloud-init, o JSON é baixado para `/opt/graylog/contentpacks/`, validado e configurado para auto-instalação pelo loader nativo do Graylog no primeiro start.

## OCI Object Storage Logs

Informe no Resource Manager:

- `Bucket de logs OCI`: bucket onde o Service Connector Hub grava os logs.
- `Prefixo dos objetos de log`: prefixo opcional, por exemplo `oci-logs/`.
- `Dias máximos de histórico dos logs`: default `7`; use `0` para processar objetos sem limite por idade.

A VM usa Instance Principal para ler o bucket. Crie um Dynamic Group para a instância e policies como:

```text
Allow dynamic-group <dynamic-group-graylog> to inspect buckets in compartment id <compartment-do-bucket> where target.bucket.name = '<nome-do-bucket>'
Allow dynamic-group <dynamic-group-graylog> to read objects in compartment id <compartment-do-bucket> where target.bucket.name = '<nome-do-bucket>'
```

O serviço local do coletor é:

```bash
sudo systemctl status oci-object-logs-to-graylog
sudo journalctl -u oci-object-logs-to-graylog -f
```

A porta GELF HTTP `12202/tcp` não fica exposta externamente; ela é publicada apenas em `127.0.0.1` para uso pelo coletor local.

## IAM Opcional

A stack tem a opção `Criar Dynamic Group e Policy`.

- `false` por padrão: não cria IAM; a VM grava a sintaxe em `/root/graylog-oci-iam-policy.txt`.
- `true`: cria um Dynamic Group restrito ao OCID da instância e uma Policy no compartment do bucket, limitada ao nome do bucket informado, para permitir leitura dos objetos.

Para o modo automático funcionar, o Resource Manager precisa ter permissão para criar Dynamic Groups e Policies. Se a organização centraliza IAM, mantenha `false` e entregue o arquivo de sintaxe gerado na VM para aplicação manual.
