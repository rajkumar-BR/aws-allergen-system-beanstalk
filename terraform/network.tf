# Elastic Beanstalk needs at least 2 subnets in 2 different AZs for its
# load balancer. Left unset, EB tries to auto-discover subnets across every
# AZ the account can see - which fails if an AZ is listed but has no actual
# default subnet in this account (as seen on account_a's us-east-1c).
# Querying real subnets explicitly avoids that guesswork.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}