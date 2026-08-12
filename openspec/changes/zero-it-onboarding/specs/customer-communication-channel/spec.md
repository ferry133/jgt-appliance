## ADDED Requirements

### Requirement: The onboarding channel runs on the operator side

Onboarding happens before the customer's cluster exists, so the channel MUST NOT depend on it. It SHALL be deployed alongside the factory agent, independently of any customer cluster.

#### Scenario: Channel available before any cluster exists
- **WHEN** a customer begins onboarding and no cluster has been created for them
- **THEN** the channel is reachable and able to conduct the conversation

#### Scenario: Channel survives customer cluster failure
- **WHEN** a customer's cluster is unreachable or has been destroyed
- **THEN** the channel remains available to that customer

#### Scenario: Onboarding channel is distinct from in-cluster bots
- **WHEN** the deployment is inspected
- **THEN** the onboarding channel is a separate deployment from any messaging application shipped as a customer cluster extra

### Requirement: The channel uses a messaging platform the customer already has

The customer SHALL NOT be required to install a new application in order to be onboarded. The channel SHALL use a platform already present on a typical customer's phone.

#### Scenario: No installation required for onboarding
- **WHEN** the customer begins onboarding
- **THEN** they use an application they already have, and are not asked to install anything

#### Scenario: Joining is a single scan
- **WHEN** the customer scans the code supplied in the box
- **THEN** they are connected to the channel and the conversation begins

### Requirement: The channel collects the customer's inputs conversationally

Whatever the customer must supply SHALL be collected through the conversation, not through a form the customer must find or a file they must edit.

#### Scenario: Inputs collected in conversation
- **WHEN** the channel needs a customer-supplied value
- **THEN** it asks for it as a question and records the answer against the work order

#### Scenario: Answers are bound to the right work order
- **WHEN** a customer answers a question
- **THEN** the answer is associated with that customer's work order and no other

### Requirement: The channel pushes provisioning progress

The customer SHALL receive progress without asking. Progress messages SHALL be phrased in terms of what it means for the customer, not in terms of internal stages.

#### Scenario: Stage change reaches the customer
- **WHEN** the work order advances a stage
- **THEN** the customer receives a message describing what has happened in non-technical terms

#### Scenario: Completion is delivered through the channel
- **WHEN** provisioning completes
- **THEN** the customer receives the address of their system and how to sign in

### Requirement: The channel can request and receive photographs

Some on-site facts can only be established visually. The channel SHALL be able to ask the customer to photograph something and receive the image.

#### Scenario: Photograph requested and received
- **WHEN** a diagnostic step requires visual confirmation
- **THEN** the channel asks the customer to photograph the specified thing and receives the image

#### Scenario: Request specifies what to photograph
- **WHEN** a photograph is requested
- **THEN** the request identifies precisely what to point the camera at, in terms the customer can follow

### Requirement: The channel conducts guided troubleshooting and escalates

When provisioning stalls the channel SHALL guide the customer through the checks a non-technical person can perform, and escalate to a human when those are exhausted.

#### Scenario: Guided checks offered on stall
- **WHEN** a work order stalls in a stage with known on-site causes
- **THEN** the channel walks the customer through the corresponding physical checks, one at a time

#### Scenario: Escalation when checks are exhausted
- **WHEN** the guided checks do not resolve the situation
- **THEN** the channel escalates to a human and tells the customer that a person will contact them

#### Scenario: Customer-reported findings reach the work order
- **WHEN** the customer reports an observation or sends a photograph
- **THEN** it is recorded on the work order as evidence

### Requirement: The channel never exposes credentials

The channel carries operational information to a non-technical customer over a third-party platform. It SHALL NOT transmit key material, tokens, or passwords.

#### Scenario: No secrets in messages
- **WHEN** any message is sent to the customer
- **THEN** it contains no key material, token, or password
