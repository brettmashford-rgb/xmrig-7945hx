//! Offline adapter to the pinned official CPU verifier, not independent mining code.
//! There is no network code. Cargo downloads build dependencies separately.
use anyhow::{Context, Result, bail, ensure};
use base64::{Engine, engine::general_purpose::STANDARD};
use rand::{SeedableRng, rngs::StdRng};
use serde::{Deserialize, Serialize};
use std::{env, fs, path::Path};
use zk_pow::{
    api::{
        proof::{IncompleteBlockHeader, MMAType, MiningConfiguration, PeriodicPattern},
        proof_utils::{CompiledPublicParams, compute_jackpot_hash},
        verify::verify_plain_proof,
    },
    circuit::{chip::compute_jackpot, pearl_noise::compute_noise},
    ffi::{mine::try_mine_one, plain_proof::{PlainProof, check_cert_version_eligible}},
};

const MAX_INPUT: u64 = 16 * 1024 * 1024;
const MAX_PROOF: usize = 8 * 1024 * 1024;
const SOURCE: &str = "82e6eee7076aafe10123e08db78f100d270c0582";

#[derive(Serialize, Deserialize)]
struct VerificationInput {
    cert_version: u32,
    header_base64: String,
    plain_proof_base64: String,
    #[serde(default)]
    share_nbits: Option<u32>,
}

fn read_input(path: &Path) -> Result<VerificationInput> {
    ensure!(fs::metadata(path)?.len() <= MAX_INPUT, "input exceeds 16 MiB");
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}

fn decode(input: &VerificationInput) -> Result<(IncompleteBlockHeader, PlainProof)> {
    let header_bytes = STANDARD.decode(&input.header_base64)?;
    let header = IncompleteBlockHeader::from_bytes(&header_bytes)?;
    ensure!(input.plain_proof_base64.len() <= MAX_PROOF.div_ceil(3) * 4, "proof exceeds 8 MiB");
    let bytes = STANDARD.decode(&input.plain_proof_base64)?;
    ensure!(bytes.len() <= MAX_PROOF, "proof exceeds 8 MiB");
    let proof = PlainProof::deserialize_compat(&bytes)?;
    Ok((header, proof))
}

fn verify(input: &VerificationInput) -> Result<()> {
    let (header, proof) = decode(input)?;
    let version = check_cert_version_eligible(input.cert_version, &proof)?;
    verify_plain_proof(&header, &proof, input.share_nbits, version.seed_derivation())
}

fn fixture(version: u32) -> Result<serde_json::Value> {
    ensure!(version == 2 || version == 3, "fixture supports V2 or V3");
    // Easy offline test target. This is not a live pool job or accepted share.
    let header = IncompleteBlockHeader {
        version: 0,
        prev_block: [1; 32],
        merkle_root: [2; 32],
        timestamp: 0x66666666,
        nbits: 0x207fffff,
    };
    let pattern = PeriodicPattern::from_list(&[0, 1, 8, 9, 64, 65, 72, 73])?;
    let k = if version == 3 { 4096 } else { 2048 };
    let config = MiningConfiguration {
        common_dim: k, rank: 128, mma_type: MMAType::Int7xInt7ToInt32,
        rows_pattern: pattern, cols_pattern: pattern, moe: None,
    };
    let mut rng = StdRng::seed_from_u64(0x5060);
    let derivation = if version == 3 {
        zk_pow::api::proof::SeedDerivation::Salted
    } else {
        zk_pow::api::proof::SeedDerivation::Legacy
    };
    let proof = try_mine_one(&mut rng, 128, 128, k as usize, header, config, None, false, derivation)?
        .context("no offline fixture found")?;
    let input = VerificationInput {
        cert_version: version,
        header_base64: STANDARD.encode(header.to_bytes()),
        plain_proof_base64: STANDARD.encode(bincode::serialize(&proof)?),
        share_nbits: None,
    };
    // Exercise serialization/deserialization and the public verifier entry point.
    verify(&input)?;
    let (private, public) = proof.parse_proof(header, derivation)?;
    let compiled = CompiledPublicParams::from(&public);
    let noise = compute_noise(&compiled);
    let jackpot = compute_jackpot(&compiled, &private.s_a, &private.s_b, &noise);
    let digest = compute_jackpot_hash(&jackpot, compiled.a_noise_seed());
    Ok(serde_json::json!({
        "provenance": {"upstream_commit": SOURCE, "generator": "pinned official try_mine_one", "rng_seed": "0x5060", "scope": "offline synthetic; not a pool-accepted share"},
        "cert_version": input.cert_version,
        "header_base64": input.header_base64,
        "plain_proof_base64": input.plain_proof_base64,
        "share_nbits": input.share_nbits,
        "m": proof.m, "n": proof.n, "k": proof.k, "rank": proof.noise_rank,
        "config_base64": STANDARD.encode(config.to_bytes()),
        "a_rows": public.a_rows_indices(), "b_cols": public.b_cols_indices(),
        "job_key": compiled.job_key,
        "root_a": public.hash_a, "root_bt": public.hash_b,
        "b_noise_seed": compiled.commitment_hash.0,
        "a_noise_seed": compiled.commitment_hash.1,
        "opened_a": private.s_a, "opened_bt": private.s_b,
        "noise_a": noise.a, "noise_bt": noise.b,
        "jackpot_u32": jackpot, "jackpot_hash": digest,
        "verified_by_official_cpu": true,
    }))
}

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("verify") if args.len() == 3 => {
            verify(&read_input(Path::new(&args[2]))?)?;
            println!("VALID: official offline CPU verifier; not a pool verdict");
        }
        Some("fixture") if args.len() == 4 => {
            let version: u32 = args[2].parse()?;
            fs::write(&args[3], serde_json::to_vec_pretty(&fixture(version)?)?)?;
            println!("Wrote official-CPU-verified offline V{version} fixture");
        }
        _ => bail!("usage: pearl-cpu-oracle verify INPUT.json | fixture 2|3 OUTPUT.json"),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generated_v2_and_v3_proofs_verify_and_tampering_fails() -> Result<()> {
        for version in [2, 3] {
            let value = fixture(version)?;
            let mut input: VerificationInput = serde_json::from_value(value)?;
            verify(&input)?;
            // The easy target accepts every jackpot. PlainProof does not contain
            // an expected jackpot hash, so changing seed context alone need not
            // reject it here. Exact V2/V3 seed/transcript/digest comparisons live
            // in the independent Python tests; cert_version must be trusted input.
            let original_proof = input.plain_proof_base64.clone();
            let (_, mut changed) = decode(&input)?;
            changed.a.proof.leaf_data[0][0] ^= 1;
            input.plain_proof_base64 = STANDARD.encode(bincode::serialize(&changed)?);
            ensure!(verify(&input).is_err(), "changed matrix opening was accepted");
            input.plain_proof_base64 = original_proof;
            input.share_nbits = Some(0x01010000);
            ensure!(verify(&input).is_err(), "fixture cleared an intentionally tiny share target");
            input.share_nbits = None;
            let mut h = STANDARD.decode(&input.header_base64)?;
            h[4] ^= 1;
            input.header_base64 = STANDARD.encode(h);
            ensure!(verify(&input).is_err(), "changed header was accepted");
        }
        Ok(())
    }
}
