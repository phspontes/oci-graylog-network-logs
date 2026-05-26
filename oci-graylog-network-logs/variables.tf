variable "tenancy_ocid" {
  description = "OCID da tenancy."
  type        = string
}

variable "region" {
  description = "Regiao OCI onde os recursos serao criados."
  type        = string
}

variable "instance_compartment_ocid" {
  description = "OCID do compartment onde a VM e o NSG serao criados."
  type        = string
}

variable "vcn_compartment_ocid" {
  description = "OCID do compartment onde a VCN existente sera selecionada."
  type        = string
}

variable "subnet_compartment_ocid" {
  description = "OCID do compartment onde a subnet existente sera selecionada."
  type        = string
}

variable "vcn_ocid" {
  description = "OCID da VCN existente."
  type        = string
}

variable "subnet_ocid" {
  description = "OCID da subnet existente para a VM."
  type        = string
}

variable "instance_name" {
  description = "Nome da instancia."
  type        = string
  default     = "graylog-ol9"
}

variable "ssh_public_key" {
  description = "Chave publica SSH para o usuario opc."
  type        = string
  sensitive   = true
}

variable "shape" {
  description = "Shape da instancia. Minimo recomendado: VM.Standard.E5.Flex. Shapes Flex permitem configurar OCPUs e memoria."
  type        = string
  default     = "VM.Standard.E5.Flex"
}

variable "ocpus" {
  description = "Numero de OCPUs para shapes Flex. Minimo recomendado: 1."
  type        = number
  default     = 1
}

variable "memory_in_gbs" {
  description = "Memoria em GB para shapes Flex. Minimo recomendado: 12."
  type        = number
  default     = 12
}

variable "boot_volume_size_in_gbs" {
  description = "Tamanho do disco de boot em GB. Minimo recomendado: 100."
  type        = number
  default     = 100
}

variable "assign_public_ip" {
  description = "Atribuir IP publico na VNIC primaria."
  type        = bool
  default     = true
}

variable "private_ip" {
  description = "IP privado opcional para a VNIC primaria. Deixe vazio para a OCI alocar automaticamente."
  type        = string
  default     = ""
}

variable "ssh_source_cidr" {
  description = "CIDR autorizado para SSH."
  type        = string
  default     = "0.0.0.0/0"
}

variable "graylog_source_cidr" {
  description = "CIDR autorizado para a interface web do Graylog."
  type        = string
  default     = "0.0.0.0/0"
}

variable "graylog_version" {
  description = "Tag principal das imagens Graylog."
  type        = string
  default     = "7.1"
}

variable "graylog_timezone" {
  description = "Timezone configurado no Graylog."
  type        = string
  default     = "America/Sao_Paulo"
}


variable "oci_log_bucket_compartment_ocid" {
  description = "OCID do compartment onde esta o bucket Object Storage de logs."
  type        = string
}

variable "oci_log_bucket_name" {
  description = "Nome do bucket Object Storage que recebe os logs do OCI Logging via Service Connector Hub."
  type        = string
}

variable "oci_log_object_prefix" {
  description = "Prefixo dos objetos de log dentro do bucket. Deixe vazio para ler o bucket inteiro."
  type        = string
  default     = ""
}

variable "oci_log_max_object_age_days" {
  description = "Processar somente objetos modificados nos ultimos N dias. Use 0 para nao limitar por idade."
  type        = number
  default     = 7
}


variable "collector_script_url" {
  description = "URL raw do script Python que coleta logs do Object Storage e envia para o Graylog."
  type        = string
  default     = "https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci_object_storage_logs_to_graylog.py"
}


variable "create_iam_policy" {
  description = "Criar Dynamic Group e Policy para a VM ler objetos do bucket de logs. Requer permissoes IAM no Resource Manager."
  type        = bool
  default     = false
}


variable "graylog_content_pack_url" {
  description = "URL raw opcional de um Content Pack JSON para importar e instalar automaticamente no Graylog. Deixe vazio para nao instalar."
  type        = string
  default     = "https://raw.githubusercontent.com/phspontes/oci-graylog-network-logs/refs/heads/main/scripts/oci-vcn-flow-dashboard-final.json"
}
