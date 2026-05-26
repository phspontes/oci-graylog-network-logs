terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0"
    }
  }
}

provider "oci" {
  region = var.region
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "oracle_linux_9" {
  compartment_id           = var.instance_compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "9"
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
  state                    = "AVAILABLE"
}

locals {
  is_flex_shape      = can(regex("Flex$", var.shape))
  image_id           = data.oci_core_images.oracle_linux_9.images[0].id
  iam_name_prefix    = substr(replace(var.instance_name, "/[^A-Za-z0-9_.-]/", "-"), 0, 80)
  dynamic_group_name = "${local.iam_name_prefix}-dg"
  iam_policy_name    = "${local.iam_name_prefix}-object-logs-policy"

  cloud_init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    region                          = var.region
    graylog_version                 = var.graylog_version
    graylog_timezone                = var.graylog_timezone
    oci_log_bucket_compartment_ocid = var.oci_log_bucket_compartment_ocid
    oci_log_bucket_name             = var.oci_log_bucket_name
    oci_log_object_prefix           = var.oci_log_object_prefix
    oci_log_max_object_age_days     = var.oci_log_max_object_age_days
    collector_script_url            = var.collector_script_url
    graylog_content_pack_url        = var.graylog_content_pack_url
    create_iam_policy               = var.create_iam_policy
    dynamic_group_name              = local.dynamic_group_name
  })
}

resource "oci_core_network_security_group" "graylog" {
  compartment_id = var.vcn_compartment_ocid
  vcn_id         = var.vcn_ocid
  display_name   = "${var.instance_name}-nsg"
}

resource "oci_core_network_security_group_security_rule" "egress_all" {
  network_security_group_id = oci_core_network_security_group.graylog.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  stateless                 = false
}

resource "oci_core_network_security_group_security_rule" "ssh" {
  network_security_group_id = oci_core_network_security_group.graylog.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.ssh_source_cidr
  source_type               = "CIDR_BLOCK"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "graylog_web" {
  network_security_group_id = oci_core_network_security_group.graylog.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.graylog_source_cidr
  source_type               = "CIDR_BLOCK"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 9000
      max = 9000
    }
  }
}

resource "oci_core_instance" "graylog" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.instance_compartment_ocid
  display_name        = var.instance_name
  shape               = var.shape

  dynamic "shape_config" {
    for_each = local.is_flex_shape ? [1] : []
    content {
      ocpus         = var.ocpus
      memory_in_gbs = var.memory_in_gbs
    }
  }

  create_vnic_details {
    assign_public_ip = var.assign_public_ip
    display_name     = "${var.instance_name}-vnic"
    hostname_label   = "graylog"
    nsg_ids          = [oci_core_network_security_group.graylog.id]
    private_ip       = trimspace(var.private_ip) != "" ? trimspace(var.private_ip) : null
    subnet_id        = var.subnet_ocid
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(local.cloud_init)
  }

  source_details {
    source_type             = "image"
    source_id               = local.image_id
    boot_volume_size_in_gbs = var.boot_volume_size_in_gbs
  }
}

resource "oci_identity_dynamic_group" "graylog" {
  count          = var.create_iam_policy ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = local.dynamic_group_name
  description    = "Instance principal para ${var.instance_name} ler logs arquivados no Object Storage."
  matching_rule  = "ALL {instance.id = '${oci_core_instance.graylog.id}'}"
}

resource "oci_identity_policy" "graylog_object_logs" {
  count          = var.create_iam_policy ? 1 : 0
  compartment_id = var.oci_log_bucket_compartment_ocid
  name           = local.iam_policy_name
  description    = "Permite que ${local.dynamic_group_name} leia objetos do bucket ${var.oci_log_bucket_name}."

  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.graylog[0].name} to inspect buckets in compartment id ${var.oci_log_bucket_compartment_ocid} where target.bucket.name = '${var.oci_log_bucket_name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.graylog[0].name} to read objects in compartment id ${var.oci_log_bucket_compartment_ocid} where target.bucket.name = '${var.oci_log_bucket_name}'",
  ]
}
