"""
policy_tuner — Trace-driven policy analysis and suggestion layer.

This module analyzes runtime data (traces, approvals, policy history) and
produces structured governance observations:

  - TuningSignal : a pattern in execution data that warrants review
  - PolicySmell  : a structural quality issue in policy configuration
  - Suggestion   : a conservative candidate action for human review

Key classes:
  PolicyAnalyzer     — detects signals and smells from raw data
  SuggestionGenerator — generates suggestions from signals and smells
  TunerReporter      — formats the report as JSON or Markdown

Typical usage:
  from agent_hypervisor.policy_tuner import PolicyAnalyzer, SuggestionGenerator, TunerReporter

  analyzer  = PolicyAnalyzer()
  gen       = SuggestionGenerator()
  reporter  = TunerReporter()

  report = analyzer.analyze(traces, approvals, policy_history)
  report = gen.generate(report)
  print(reporter.render(report, format="markdown"))
"""

from .analyzer import PolicyAnalyzer
from .models import (
    PolicySmell,
    Severity,
    SignalCategory,
    SmellType,
    Suggestion,
    SuggestionType,
    TunerReport,
    TuningSignal,
)
from .reporter import TunerReporter
from .suggestions import SuggestionGenerator

__all__ = [
    "PolicyAnalyzer",
    "SuggestionGenerator",
    "TunerReporter",
    "TunerReport",
    "TuningSignal",
    "PolicySmell",
    "Suggestion",
    "SignalCategory",
    "Severity",
    "SmellType",
    "SuggestionType",
]
