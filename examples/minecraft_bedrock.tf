# ================================================================
# Example: Minecraft Bedrock server
#
# See https://github.com/itzg/docker-minecraft-bedrock-server
# ================================================================

module "example_bedrock" {
  id       = "ExampleBedrock"
  game     = "minecraft-bedrock"
  hostname = "examplebedrock.duckdns.org"

  # DDNS
  duckdns_token = var.duckdns_token

  # Region (change these to desired region)
  base_region = module.region_us-east-2.base_region
  providers   = { aws = aws.us-east-2 }
  az          = "us-east-2a"

  # ------------ Common values (just copy and paste) -------------
  source                     = "./server"
  iam_role_dlm_lifecycle_arn = module.global.iam_role_dlm_lifecycle_arn
  # --------------------------------------------------------------
}
