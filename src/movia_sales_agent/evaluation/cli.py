from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from movia_sales_agent.config.settings import Settings, get_settings
from movia_sales_agent.evaluation.dataset import (
    DEFAULT_DATASET_PATH,
    load_validation_dataset,
    validate_dataset,
)
from movia_sales_agent.evaluation.reporting import DEFAULT_OUTPUT_ROOT, write_reports
from movia_sales_agent.evaluation.runner import EvaluationRunner
from movia_sales_agent.evaluation.analyzer_v3_targeted import (
    DEFAULT_TARGETED_MANIFEST,
    DEFAULT_TARGETED_OUTPUT_ROOT,
    run_targeted_validation,
)
from movia_sales_agent.evaluation.phase4_supplementary import (
    DEFAULT_SUPPLEMENTARY_MANIFEST,
    DEFAULT_SUPPLEMENTARY_OUTPUT_ROOT,
    run_phase4_supplementary_live,
)
from movia_sales_agent.evaluation.adaptive_hybrid import (
    DEFAULT_ADAPTIVE_OUTPUT_ROOT,
    run_adaptive_hybrid_pilot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="movia-eval",
        description="Capability-driven validation harness for the MovIA sales agent.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-dataset", help="Validate the scenario JSON.")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)

    run = subparsers.add_parser("run", help="Replay scripted validation scenarios.")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    run.add_argument("--scenario", default="all")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--max-turns", type=int)
    run.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    run.add_argument("--offline", action="store_true")
    run.add_argument("--skip-ragas", action="store_true")
    run.add_argument("--skip-deepeval", action="store_true")
    run.add_argument("--skip-response-quality", action="store_true")
    run.add_argument(
        "--llm-response-quality",
        action="store_true",
        help="Use the configured evaluation model for response-quality judging.",
    )
    run.add_argument(
        "--no-fail-exit",
        action="store_true",
        help="Return exit code 0 even when the evaluation does not pass.",
    )

    targeted = subparsers.add_parser(
        "analyzer-v3-targeted",
        help="Run the Phase 4 targeted Analyzer V3 contract validation.",
    )
    targeted.add_argument("--manifest", type=Path, default=DEFAULT_TARGETED_MANIFEST)
    targeted.add_argument("--output-root", type=Path, default=DEFAULT_TARGETED_OUTPUT_ROOT)
    targeted.add_argument(
        "--mode",
        choices=["both", "analyzer-only", "live-agent"],
        default="both",
    )
    targeted.add_argument("--offline", action="store_true")
    targeted.add_argument("--previous-run", type=Path, action="append", default=[])
    targeted.add_argument("--skip-docs", action="store_true")
    targeted.add_argument(
        "--no-fail-exit",
        action="store_true",
        help="Return exit code 0 even when targeted gates fail.",
    )

    supplementary = subparsers.add_parser(
        "phase4-supplementary-live",
        help="Run the supplementary live Phase 4 validation once.",
    )
    supplementary.add_argument("--manifest", type=Path, default=DEFAULT_SUPPLEMENTARY_MANIFEST)
    supplementary.add_argument("--output-root", type=Path, default=DEFAULT_SUPPLEMENTARY_OUTPUT_ROOT)
    supplementary.add_argument(
        "--no-fail-exit",
        action="store_true",
        help="Return exit code 0 even when supplementary gates fail.",
    )

    adaptive = subparsers.add_parser(
        "adaptive-hybrid-pilot",
        help="Run the Adaptive Hybrid pilot evaluation once.",
    )
    adaptive.add_argument("--output-root", type=Path, default=DEFAULT_ADAPTIVE_OUTPUT_ROOT)
    adaptive.add_argument("--max-turns", type=int, default=10)
    adaptive.add_argument(
        "--no-fail-exit",
        action="store_true",
        help="Return exit code 0 even when the pilot fails.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-dataset":
        dataset = load_validation_dataset(args.dataset)
        summary = validate_dataset(dataset)
        print(summary.model_dump_json(indent=2))
        return 0 if summary.valid else 1

    if args.command == "analyzer-v3-targeted":
        settings = offline_settings() if args.offline else get_settings()
        result = run_targeted_validation(
            manifest_path=args.manifest,
            output_root=args.output_root,
            mode=args.mode,
            settings=settings,
            offline=args.offline,
            previous_run_paths=args.previous_run or None,
            write_docs=not args.skip_docs,
        )
        print(
            json.dumps(
                {
                    "run_id": result["run_id"],
                    "passed": result["passed"],
                    "terminal_status": result["terminal_status"],
                    "hard_failures": result["gate_summary"]["hard_failures"],
                    "output_dir": result["output_dir"],
                    "summary": str(Path(result["output_dir"]) / "summary.md"),
                    "gate_summary": str(Path(result["output_dir"]) / "gate_summary.json"),
                },
                indent=2,
            )
        )
        if args.no_fail_exit:
            return 0
        return 0 if result["passed"] else 1

    if args.command == "phase4-supplementary-live":
        result = run_phase4_supplementary_live(
            manifest_path=args.manifest,
            output_root=args.output_root,
            settings=get_settings(),
        )
        print(
            json.dumps(
                {
                    "run_id": result["run_id"],
                    "passed": result["passed"],
                    "status": result["status"],
                    "hard_failures": result["gate_summary"]["hard_failures"],
                    "output_dir": result["output_dir"],
                    "summary": str(Path(result["output_dir"]) / "summary.md"),
                    "gate_summary": str(Path(result["output_dir"]) / "gate_summary.json"),
                    "run_json": str(Path(result["output_dir"]) / "run.json"),
                    "conversation_transcript": str(Path(result["output_dir"]) / "conversation_transcript.md"),
                },
                indent=2,
            )
        )
        if args.no_fail_exit:
            return 0
        return 0 if result["passed"] else 1

    if args.command == "adaptive-hybrid-pilot":
        result = run_adaptive_hybrid_pilot(
            output_root=args.output_root,
            settings=get_settings(),
            max_turns=args.max_turns,
        )
        output_dir = Path(result["output_dir"])
        print(
            json.dumps(
                {
                    "run_id": result["run_id"],
                    "passed": result["passed"],
                    "status": result["final_status"],
                    "hard_failures": result["gate_summary"]["hard_failures"],
                    "ready_for_limited_internal_pilot": result["ready_for_limited_internal_pilot"],
                    "ready_for_external_leads": result["ready_for_external_leads"],
                    "output_dir": str(output_dir),
                    "summary": str(output_dir / "summary.md"),
                    "run_json": str(output_dir / "run.json"),
                    "conversations": str(output_dir / "conversations.md"),
                    "conversation_scores": str(output_dir / "conversation_scores.json"),
                    "cost_latency": str(output_dir / "cost_latency.json"),
                },
                indent=2,
            )
        )
        if args.no_fail_exit:
            return 0
        return 0 if result["passed"] else 1

    settings = offline_settings() if args.offline else get_settings()
    runner = EvaluationRunner(
        settings=settings,
        dataset_path=args.dataset,
        enable_ragas=not args.skip_ragas and not args.offline,
        enable_deepeval=not args.skip_deepeval and not args.offline,
        enable_response_quality=not args.skip_response_quality,
        enable_response_quality_llm=args.llm_response_quality and not args.offline,
    )
    result = runner.run(
        scenario_id=args.scenario,
        repeat=args.repeat,
        max_turns=args.max_turns,
        offline=args.offline,
    )
    output = write_reports(result, args.output_root)
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "passed": result.passed,
                "overall_score": result.overall_score,
                "hard_failures": len(result.hard_failures),
                "report": str(output / "summary.md"),
                "raw_result": str(output / "run.json"),
            },
            indent=2,
        )
    )
    if args.no_fail_exit:
        return 0
    return 0 if result.passed else 1


def offline_settings() -> Settings:
    return Settings(
        OPENAI_MODEL="offline",
        MOVIA_DISABLE_OPENAI=True,
        MOVIA_DISABLE_DATABASE=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
