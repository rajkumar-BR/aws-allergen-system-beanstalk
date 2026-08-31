# Elastic Beanstalk needs at least 2 subnets in 2 different AZs for its
# load balancer. Left unset, EB tries to auto-discover subnets across every
# AZ the account can see - which fails if an AZ is listed but has no actual
# default subnet in this account (as seen on account_a's us-east-1c).
# Querying real subnets explicitly avoids that guesswork.
data "aws_vpc" "default" {
  default = true
}

# Only AZs where the chosen instance type is actually offerable. us-east-1e
# (and occasionally others) don't offer t3.small, which makes Beanstalk's
# CreateEnvironment fail with "instance types aren't available in your VPC
# Subnets". We query the offerings and intersect with the default subnets.
data "aws_ec2_instance_type_offerings" "by_az" {
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
  location_type = "availability-zone"
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  # Restrict to AZs that can actually launch the instance type
  filter {
    name   = "availability-zone"
    values = data.aws_ec2_instance_type_offerings.by_az.locations
  }
}