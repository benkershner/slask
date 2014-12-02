# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

Vagrant.require_version ">= 1.5.0"

$script = <<EOS
apt-get update
apt-get install -y python-pip python-dev build-essential libffi-dev
cd /vagrant
python ./setup.py develop
EOS

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.hostname = "slask"
  config.vm.box = "opscode-ubuntu-12.04-chef"
  config.vm.box_url = "https://oss-binaries.phusionpassenger.com/vagrant/boxes/latest/ubuntu-12.04-amd64-vbox.box"
  config.vm.network :private_network, type: "dhcp"

  config.vm.provision "shell", inline: $script
end
