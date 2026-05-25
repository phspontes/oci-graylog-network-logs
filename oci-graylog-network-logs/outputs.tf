output "instance_id" {
  description = "OCID da instancia Graylog."
  value       = oci_core_instance.graylog.id
}

output "private_ip" {
  description = "IP privado da instancia."
  value       = oci_core_instance.graylog.private_ip
}

output "public_ip" {
  description = "IP publico da instancia, se atribuido."
  value       = oci_core_instance.graylog.public_ip
}

output "graylog_url" {
  description = "URL HTTP do Graylog."
  value       = "http://${coalesce(oci_core_instance.graylog.public_ip, oci_core_instance.graylog.private_ip)}:9000/"
}

output "graylog_user" {
  description = "Usuario inicial do Graylog."
  value       = "admin"
}

output "graylog_password_hint" {
  description = "Senha inicial definida pelo cloud-init."
  value       = "A senha inicial do usuario admin e o OCID da instancia: ${oci_core_instance.graylog.id}"
}


output "iam_policy_mode" {
  description = "Indica se a stack tentou criar Dynamic Group e Policy automaticamente."
  value       = var.create_iam_policy ? "automatic" : "manual"
}

output "dynamic_group_name" {
  description = "Nome do Dynamic Group usado/criado para a VM Graylog."
  value       = local.dynamic_group_name
}

output "iam_policy_hint" {
  description = "Resumo da policy necessaria caso create_iam_policy=false."
  value       = "Allow dynamic-group ${local.dynamic_group_name} to read objects in compartment id ${var.oci_log_bucket_compartment_ocid}"
}
