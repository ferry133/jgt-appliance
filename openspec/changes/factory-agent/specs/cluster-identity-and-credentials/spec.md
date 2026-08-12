## ADDED Requirements

### Requirement: Each cluster has a service identity distinct from its login identity

Two different identities SHALL exist per cluster and MUST NOT be conflated. The **service identity** holds accounts the cluster depends on, such as its Cloudflare registration address. The **login identity** is the customer's own everyday address, used to authenticate to the resident agent. Sharing one identity for both would make audit trails unable to distinguish operator actions from customer actions.

#### Scenario: Service identity holds accounts
- **WHEN** an account is registered on the cluster's behalf
- **THEN** it is registered against the cluster's service identity, not against a personal address

#### Scenario: Customer logs in as themselves
- **WHEN** the customer authenticates to the resident agent
- **THEN** they authenticate as their own identity, and the service identity is not a permitted login

#### Scenario: Actions are attributable
- **WHEN** an action is taken on the cluster
- **THEN** the audit record distinguishes whether it was taken by the operator or by the customer

### Requirement: Service identities are created through a supported automated path

Service identities SHALL be created only through an interface whose provider supports automation. Automated creation of consumer Google accounts is prohibited by that provider's terms, is gated behind SMS verification, and risks suspension of the account together with everything registered against it — so it MUST NOT be used.

#### Scenario: Identity created via supported API
- **WHEN** a new cluster's service identity is created
- **THEN** it is created through a provider interface that permits automated provisioning

#### Scenario: Consumer account signup is not attempted
- **WHEN** provisioning requires a new service identity
- **THEN** no automated consumer account signup flow is attempted

### Requirement: The customer supplies no infrastructure credentials at onboarding

Under the zero-input profile the customer SHALL NOT be asked for a DNS or CDN credential of any kind. Producing a correctly scoped token requires an account, a login, and an understanding of permission scopes — capability the profile exists precisely to avoid needing. Those values are supplied by the operator.

#### Scenario: No credential is requested from the customer
- **WHEN** a zero-input cluster is provisioned
- **THEN** the customer is asked for no API token, no account credential, and no permission configuration

#### Scenario: Operator-supplied values are still declared
- **WHEN** such a cluster's configuration is rendered
- **THEN** the DNS and CDN values are present, supplied by the operator, and validation passes without customer input

#### Scenario: Account credentials are never accepted in place of a token
- **WHEN** a customer offers an account login for an infrastructure provider
- **THEN** it is declined in favour of a scoped credential, because an account grants everything the account can reach and cannot be narrowed after the fact

### Requirement: The customer's domain is theirs from the first day

The cluster's public hostnames SHALL be under a domain the customer owns, with DNS delegated to the operator's account for management. Hosting the cluster under an operator-owned domain would make handover a rename of every hostname, and the cost of a rename falls on whoever configured a client against it — bookmarks, device configurations, pairing records, OAuth callback registrations, certificate names.

#### Scenario: Hostnames do not change at handover
- **WHEN** a cluster is handed over to its customer
- **THEN** every hostname it serves is unchanged, and no client needs reconfiguring

#### Scenario: Delegation, not ownership, transfers
- **WHEN** handover completes
- **THEN** what changes is which account manages the domain's DNS, not which domain is used

#### Scenario: Acquiring the domain is not a configuration task
- **WHEN** a customer needs a domain and cannot configure one
- **THEN** the operator may register it on the customer's behalf, so that the customer's only involvement is a purchase decision

### Requirement: The credential set per cluster is enumerated

Handover and incident response both require knowing exactly what secrets exist for a cluster. The full set SHALL be enumerated and recorded: the SOPS age key, repository access, infrastructure management access, DNS and tunnel credentials, model API credentials, and cluster administrative access.

#### Scenario: Inventory exists per cluster
- **WHEN** a cluster's credentials are reviewed
- **THEN** every secret associated with it is listed with its purpose and its holder

#### Scenario: Inventory is kept current
- **WHEN** a credential is added, rotated, or removed
- **THEN** the inventory is updated in the same operation

### Requirement: The age key is escrowed before provisioning is complete

`age.key` is generated during provisioning and is the only means of decrypting both SOPS secrets and backups. It SHALL be escrowed outside the customer site, and provisioning SHALL NOT be marked complete until escrow is confirmed.

#### Scenario: Escrow gates completion
- **WHEN** provisioning reaches its final stage without a confirmed escrow record
- **THEN** the run does not complete and the missing escrow is escalated

#### Scenario: Escrow is verifiable
- **WHEN** an operator checks whether a cluster's key is escrowed
- **THEN** a record confirms it, identifying the cluster without exposing the key

### Requirement: Credentials are rotatable without rebuilding the cluster

Every credential SHALL have a documented rotation procedure that does not require re-provisioning.

#### Scenario: Rotation procedure exists
- **WHEN** any credential must be rotated
- **THEN** a documented procedure exists for rotating it in place

#### Scenario: Age key rotation re-encrypts in place
- **WHEN** the SOPS age key is rotated
- **THEN** existing encrypted files are re-encrypted to the new key without being decrypted into the repository
