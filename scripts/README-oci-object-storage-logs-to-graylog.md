# OCI Object Storage Logs para Graylog

Script: `scripts/oci_object_storage_logs_to_graylog.py`

Fluxo recomendado quando nao precisa de tempo real:

```text
OCI Logging -> Service Connector Hub -> Object Storage -> script Python -> Graylog GELF HTTP
```

O script roda no servidor Graylog, autentica com Instance Principal, lista objetos no bucket/prefixo, baixa arquivos novos, interpreta JSON/JSON Lines/gzip e envia os eventos para um input GELF HTTP do Graylog.

## Premissas

1. Criar um bucket para arquivamento dos logs.
2. Criar um Service Connector:
   - Source: Logging
   - Target: Object Storage
   - Bucket: bucket escolhido
   - Prefix opcional, por exemplo `oci-logs/`
3. Criar no Graylog um input `GELF HTTP`, por exemplo na porta `12202`.
4. Instalar o SDK OCI na VM:

```bash
sudo dnf -y install python3-pip
sudo python3 -m pip install oci
```

## Policy OCI para a VM

A VM precisa estar em um Dynamic Group. Exemplo:

```text
Allow dynamic-group <dynamic-group-graylog> to inspect buckets in compartment <compartment-do-bucket>
Allow dynamic-group <dynamic-group-graylog> to read objects in compartment <compartment-do-bucket>
```

Se o bucket estiver em outro compartment, use o compartment do bucket.

## Teste sem enviar para o Graylog

```bash
python3 oci_object_storage_logs_to_graylog.py \
  --region sa-vinhedo-1 \
  --bucket nome-do-bucket \
  --prefix oci-logs/ \
  --once \
  --dry-run
```

## Execucao enviando para Graylog

```bash
python3 oci_object_storage_logs_to_graylog.py \
  --region sa-vinhedo-1 \
  --bucket nome-do-bucket \
  --prefix oci-logs/ \
  --graylog-url http://127.0.0.1:12202/gelf
```

## Checkpoint

Por padrao, o checkpoint fica em:

```text
/var/lib/oci-object-logs-to-graylog/state.json
```

Um objeto so e marcado como processado depois de ser enviado com sucesso. Para reprocessar durante testes:

```bash
sudo rm -f /var/lib/oci-object-logs-to-graylog/state.json
```

Ou use:

```bash
--include-processed
```

## Systemd opcional

```ini
[Unit]
Description=OCI Object Storage Logs to Graylog
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/graylog/bin/oci_object_storage_logs_to_graylog.py --region sa-vinhedo-1 --bucket nome-do-bucket --prefix oci-logs/ --graylog-url http://127.0.0.1:12202/gelf
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```
