import pulumi
import pulumi_aws as aws
import pulumi_tls as tls # New provider to generate key pair

# --- Configuration Variables ---
aws_region = pulumi.Config().get("aws:region") or "us-west-2"
instance_type = pulumi.Config().get("instanceType") or "m5.large"
my_public_ip = pulumi.Config().get("myPublicIp") # Your current public IP for SSH access (e.g., "XX.XX.XX.XX/32")

# Define a tag prefix for all resources to easily identify them
tag_prefix = "ipfs-node-pulumi"

# --- 1. Create a new VPC and Networking components ---
ipfs_vpc = aws.ec2.Vpc(f"{tag_prefix}-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={
        "Name": f"{tag_prefix}-vpc",
        "ManagedBy": "Pulumi",
    })

ipfs_subnet = aws.ec2.Subnet(f"{tag_prefix}-subnet",
    vpc_id=ipfs_vpc.id,
    cidr_block="10.0.1.0/24",
    map_public_ip_on_launch=True,
    availability_zone=f"{aws_region}a",
    tags={
        "Name": f"{tag_prefix}-subnet",
        "ManagedBy": "Pulumi",
    })

ipfs_igw = aws.ec2.InternetGateway(f"{tag_prefix}-igw",
    vpc_id=ipfs_vpc.id,
    tags={
        "Name": f"{tag_prefix}-igw",
        "ManagedBy": "Pulumi",
    })

ipfs_route_table = aws.ec2.RouteTable(f"{tag_prefix}-route-table",
    vpc_id=ipfs_vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=ipfs_igw.id,
        )
    ],
    tags={
        "Name": f"{tag_prefix}-route-table",
        "ManagedBy": "Pulumi",
    })

aws.ec2.RouteTableAssociation(f"{tag_prefix}-route-table-association",
    subnet_id=ipfs_subnet.id,
    route_table_id=ipfs_route_table.id)

# --- 2. Create a Security Group ---
ipfs_security_group = aws.ec2.SecurityGroup(f"{tag_prefix}-sg",
    vpc_id=ipfs_vpc.id,
    description="Allow SSH, IPFS Swarm, Gateway, and API traffic",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            from_port=22,
            to_port=22,
            protocol="tcp",
            cidr_blocks=[my_public_ip] if my_public_ip else ["0.0.0.0/0"],
            description="SSH access",
        ),
        aws.ec2.SecurityGroupIngressArgs(
            from_port=4001,
            to_port=4001,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
            description="IPFS Swarm (TCP)",
        ),
        aws.ec2.SecurityGroupIngressArgs(
            from_port=4001,
            to_port=4001,
            protocol="udp",
            cidr_blocks=["0.0.0.0/0"],
            description="IPFS Swarm (UDP)",
        ),
        aws.ec2.SecurityGroupIngressArgs(
            from_port=8080,
            to_port=8080,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
            description="IPFS Gateway",
        ),
        aws.ec2.SecurityGroupIngressArgs(
            from_port=5001,
            to_port=5001,
            protocol="tcp",
            cidr_blocks=[my_public_ip] if my_public_ip else ["0.0.0.0/0"],
            description="IPFS API",
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            from_port=0,
            to_port=0,
            protocol="-1",
            cidr_blocks=["0.0.0.0/0"],
        )
    ],
    tags={
        "Name": f"{tag_prefix}-sg",
        "ManagedBy": "Pulumi",
    })

# --- 3. Generate a new SSH key pair with the 'tls' provider ---
# This is a robust way to create a key pair within Pulumi code.
# The private key will be saved as an output.
key_pair = tls.PrivateKey("ipfs-key",
    algorithm="RSA")

# --- 4. Use the generated public key to create the EC2 KeyPair resource in AWS ---
# This associates the public key with your AWS account for EC2 instances.
ipfs_key_pair = aws.ec2.KeyPair(f"{tag_prefix}-key",
    key_name=f"{tag_prefix}-key",
    public_key=key_pair.public_key_openssh,
    tags={
        "ManagedBy": "Pulumi",
    })

# --- 5. Find a suitable AMI (Ubuntu 22.04 LTS) ---
try:
    ami = aws.ec2.get_ami(
        most_recent=True,
        owners=["099720109477"],
        filters=[
            aws.ec2.GetAmiFilterArgs(name="name", values=["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]),
            aws.ec2.GetAmiFilterArgs(name="virtualization-type", values=["hvm"]),
        ])
    pulumi.log.info(f"Successfully found AMI: {ami.name}")
except Exception as e:
    pulumi.log.error("Failed to find a suitable AMI. Please check your AWS region and the AMI filters.")
    raise e

# --- 6. Define User Data for EC2 Instance ---
user_data_script = f"""#!/bin/bash
sudo apt update -y
sudo apt install -y curl unzip

IPFS_VERSION="v0.29.0"
wget https://dist.ipfs.io/kubo/${{IPFS_VERSION}}/kubo_${{IPFS_VERSION}}_linux-amd64.tar.gz
tar -xvzf kubo_${{IPFS_VERSION}}_linux-amd64.tar.gz
cd kubo
sudo bash install.sh

ipfs init
ipfs config Addresses.API /ip4/0.0.0.0/tcp/5001
ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8080
ipfs config --json Swarm.EnableRelayHop true
ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST"]'

sudo tee /etc/systemd/system/ipfs.service > /dev/null <<EOT
[Unit]
Description=IPFS Daemon
After=network.target

[Service]
ExecStart=/usr/local/bin/ipfs daemon --enable-gc
RestartSec=10
Restart=on-failure
User=ubuntu
Environment="IPFS_PATH=/home/ubuntu/.ipfs"

[Install]
WantedBy=multi-user.target
EOT

sudo systemctl daemon-reload
sudo systemctl enable ipfs
sudo systemctl start ipfs
"""

# --- 7. Create the EC2 Instance ---
ipfs_instance = aws.ec2.Instance(f"{tag_prefix}-instance",
    ami=ami.id,
    instance_type=instance_type,
    key_name=ipfs_key_pair.key_name, # Use the key pair created as a Pulumi resource
    subnet_id=ipfs_subnet.id,
    vpc_security_group_ids=[ipfs_security_group.id],
    user_data=user_data_script,
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        volume_size=50,
        volume_type="gp3",
    ),
    tags={
        "Name": f"{tag_prefix}-instance",
        "ManagedBy": "Pulumi",
    })

# --- Outputs ---
# The private key material is a sensitive output and will be encrypted by Pulumi
pulumi.export("private_key", key_pair.private_key_pem)
pulumi.export("ipfs_node_public_ip", ipfs_instance.public_ip)
pulumi.export("ipfs_key_pair_name", ipfs_key_pair.key_name)
pulumi.export("ipfs_gateway_url", pulumi.Output.format("http://{}:8080/ipfs/", ipfs_instance.public_ip))
