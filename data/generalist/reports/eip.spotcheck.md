# eip: 20 random items for a spot check

Check the gold label against the linked source record.

## 1. ERC-3440 (test): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-3440.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2021-04-20)
Title: ERC-721 Editions Standard
Abstract: ERC-3440 is an ERC-721 extension specifically designed to make NFTs more robust for works of art. This extends the original ERC-721 spec by providing the ability to designate the original and limited-edition prints with a specialized enumeration extension similar to the original 721 extension built-in. The key improvement of this extension is allowing artists to designate the limited nature of their prints and provide a signed piece of data that represents their unique signature to a given token Id, much like an artist would sign a print of their work.
Requires: EIP-712, EIP-721

Which status does this proposal have now?
```

## 2. EIP-4399 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-4399.md

```
Ethereum improvement proposal (Standards Track, Core, created 2021-10-30)
Title: Supplant DIFFICULTY opcode with PREVRANDAO
Description: Expose beacon chain randomness in the EVM by supplanting DIFFICULTY opcode semantics
Abstract: This EIP supplants the semantics of the return value of existing DIFFICULTY (0x44) opcode and renames the opcode to PREVRANDAO (0x44). The return value of the DIFFICULTY (0x44) instruction after this change is the output of the randomness beacon provided by the beacon chain.
Requires: EIP-3675

What is the status of this proposal today?
```

## 3. EIP-7691 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-7691.md

```
Ethereum improvement proposal (Standards Track, Core, created 2024-04-17)
Title: Blob throughput increase
Description: Increase the number of blobs to reach a new target and max of 6 and 9 blobs per block respectively
Abstract: Increases the number of blobs in a block to provide more scale to Ethereum via L2 solution that rely on L1 data capacity.

What became of this proposal?
```

## 4. EIP-778 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-778.md

```
Ethereum improvement proposal (Standards Track, Networking, created 2017-11-23)
Title: Ethereum Node Records (ENR)
Abstract: This EIP defines Ethereum Node Records, an open format for p2p connectivity information.

What became of this proposal?
```

## 5. EIP-7783 (train): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-7783.md

```
Ethereum improvement proposal (Informational, created 2024-10-06)
Title: Add Controlled Gas Limit Increase Strategy
Description: Adds a controlled gas limit increase strategy.
Abstract: This proposal describes the introduction in clients of a controlled gas limit increase strategy to determine the gas limit of a specific block and set as default with conservative parameters, while keeping the possibility to change it in the future to a fixed value.

Which status does this proposal have now?
```

## 6. EIP-1052 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-1052.md

```
Ethereum improvement proposal (Standards Track, Core, created 2018-05-02)
Title: EXTCODEHASH opcode
Abstract: This EIP specifies a new opcode, which returns the keccak256 hash of a contract's code.
Requires: EIP-161

Which of these is the proposal's current status?
```

## 7. ERC-4834 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-4834.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2022-02-22)
Title: Hierarchical Domains
Description: Extremely generic name resolution
Abstract: This is a standard for generic name resolution with arbitrarily complex access control and resolution. It permits a contract that implements this EIP (referred to as a "domain" hereafter) to be addressable with a more human-friendly name, with a similar purpose to ERC-137 (also known as "ENS").

Where does this proposal stand today?
```

## 8. EIP-140 (test): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-140.md

```
Ethereum improvement proposal (Standards Track, Core, created 2017-02-06)
Title: REVERT instruction
Abstract: The REVERT instruction will stop execution, roll back all state changes done so far and provide a pointer to a memory section, which can be interpreted as an error code or message. While doing so, it will not consume all the remaining gas.

Where does this proposal stand today?
```

## 9. EIP-1240 (test): gold = Withdrawn by its authors

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-1240.md

```
Ethereum improvement proposal (Standards Track, Core, created 2018-07-21)
Title: Remove Difficulty Bomb
Abstract: Starting with FORKBLOCKNUMBER the client will calculate the difficulty without considering the current block number.

What became of this proposal?
```

## 10. ERC-6808 (select): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-6808.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2023-03-31)
Title: Fungible Key Bound Token
Description: An interface for Fungible Key Bound Tokens, also known as a FKBT.
Abstract: A standard interface for Fungible Key Bound Tokens (FKBT/s), a subset of the more general Key Bound Tokens (KBT/s). The following standardizes an API for tokens within smart contracts and provides basic functionality to the addBindings function. This function designates Key Wallets[^1], which are responsible for conducting a Safe Transfer[^2]. During this process, FKBT's are safely approved so they can be spent by the user or an on-chain third-party entity. The premise of FKBT's is to provide fully optional security features built directly into the fungible asset, via the concept of allow found in the allowTransfer and allowApproval functions. These functions are called by one of the Key Wallets[^1] and allow the Holding Wallet[^3] to either call the already familiar transfer and approve function found in ERC-20. Responsibility for the FKBT is therefore split.
Requires: EIP-20

What became of this proposal?
```

## 11. EIP-2488 (train): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-2488.md

```
Ethereum improvement proposal (Standards Track, Core, created 2019-12-20)
Title: Deprecate the CALLCODE opcode
Abstract: Deprecate CALLCODE in a somewhat backwards compatible way, by making it always return failure.
Requires: EIP-7

What became of this proposal?
```

## 12. ERC-1203 (train): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-1203.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2018-07-01)
Title: ERC-1203 Multi-Class Token Standard (ERC-20 Extension)
Abstract: The following standard allows for the implementation of a standard API for MCTs within smart contracts. This standard provides basic functionality to track, transfer, and convert MCTs.

Which status does this proposal have now?
```

## 13. ERC-2771 (test): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-2771.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2020-07-01)
Title: Secure Protocol for Native Meta Transactions
Description: A contract interface for receiving meta transactions through a trusted forwarder
Abstract: This EIP defines a contract-level protocol for Recipient contracts to accept meta-transactions through trusted Forwarder contracts. No protocol changes are made. Recipient contracts are sent the effective msg.sender (referred to as msgSender()) and msg.data (referred to as msgData()) by appending additional calldata.

What is the status of this proposal today?
```

## 14. ERC-6454 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-6454.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2023-01-31)
Title: Minimal Transferable NFT detection interface
Description: A minimal extension to identify the transferability of Non-Fungible Tokens.
Abstract: The Minimalistic Transferable interface for Non-Fungible Tokens standard extends ERC-721 by introducing the ability to identify whether an NFT can be transferred or not. This proposal introduces the ability to prevent a token from being transferred from their owner, making them bound to the externally owned account, abstracted account, smart contract or token that owns it.
Requires: EIP-165, EIP-721

What is the status of this proposal today?
```

## 15. EIP-609 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-609.md

```
Ethereum improvement proposal (Meta, created 2017-04-23)
Title: Hardfork Meta: Byzantium
Abstract: This specifies the changes included in the hard fork named Byzantium.
Requires: EIP-100, EIP-140, EIP-196, EIP-197, EIP-198, EIP-211, EIP-214, EIP-607, EIP-649, EIP-658

What is the status of this proposal today?
```

## 16. ERC-4361 (test): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-4361.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2021-10-11)
Title: Sign-In with Ethereum
Description: Off-chain authentication for Ethereum accounts to establish sessions.
Abstract: Sign-In with Ethereum describes how Ethereum accounts authenticate with off-chain services by signing a standard message format parameterized by scope, session details, and security mechanisms (e.g., a nonce). The goals of this specification are to provide a self-custodied alternative to centralized identity providers, improve interoperability across off-chain services for Ethereum-based authentication, and provide wallet vendors a consistent machine-readable message format to achieve improved user experiences and consent management.
Requires: EIP-55, EIP-137, EIP-155, EIP-191, EIP-1271, EIP-1328

Which of these is the proposal's current status?
```

## 17. ERC-3475 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-3475.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2021-04-05)
Title: Abstract Storage Bonds
Description: Interface for creating tokenized obligations with abstract on-chain metadata storage
Abstract: - This EIP allows the creation of tokenized obligations with abstract on-chain metadata storage. Issuing bonds with multiple redemption data cannot be achieved with existing token standards. - This EIP enables each bond class ID to represent a new configurable token type and corresponding to each class, corresponding bond nonces to represent an issuing condition or any other form of data in uint256. Every single nonce of a bond class can have its metadata, supply, and other redemption conditions. - Bonds created by this EIP can also be batched for issuance/redemption conditions for efficiency on gas costs and UX side. And finally, bonds created from this standard can be divided and exchanged in a secondary market.
Requires: EIP-20, EIP-721, EIP-1155

Which status does this proposal have now?
```

## 18. EIP-5345 (test): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/EIPs/blob/d4c575521d99ec881a444ab3af604e684b5f0743/EIPS/eip-5345.md

```
Ethereum improvement proposal (Standards Track, Interface, created 2022-07-26)
Title: Silent Signing Extension for JSON-RPC
Description: Temporary transaction signing without user interaction
Abstract: Mobile applications supporting lots of transactions might become a source of bad user experience due to uncontrolled switching between the wallet's and application's UI. By this proposal, we would like to introduce the means to sign and send wallet transactions without the need for user participation. This feature can be implemented by providing user consent for a specific time duration. We call the feature Silent Signing.

Which of these is the proposal's current status?
```

## 19. ERC-3234 (test): gold = Stagnant (inactive for six months or more, never finished)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-3234.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2021-01-31)
Title: Batch Flash Loans
Abstract: This ERC provides standard interfaces and processes for multiple-asset flash loans.

What is the status of this proposal today?
```

## 20. ERC-7627 (train): gold = Final (accepted and part of the standard)

https://github.com/ethereum/ERCs/blob/15568610b3583f0709aaa31b71611a39ed49af40/ERCS/erc-7627.md

```
Ethereum improvement proposal (Standards Track, ERC, created 2024-02-19)
Title: Secure Messaging Protocol
Description: End-to-end encryption for sending messages between users.
Abstract: This proposal implements the capability to securely exchange encrypted messages on-chain. Users can register their public keys and encryption algorithms by registration and subsequently send encrypted messages to other users using their addresses. The interface also includes enumerations for public key algorithms and a structure for user information to support various encryption algorithms and user information management.

Which status does this proposal have now?
```

