using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using Xunit;
using static TeklaHarness.Core.Tests.PlanFixtures;

namespace TeklaHarness.Core.Tests;

/// <summary>
/// ADR-0012 decisions 5–8. The dangerous outputs are a <c>create</c> for a member that may already
/// exist (a duplicate SPEC_ID in a real model) and a <c>skip</c>/<c>retag</c> of an object that is
/// not the spec item (a wrong member trusted silently).
/// </summary>
public sealed class ResumePlannerTests
{
    // ---- helpers

    private static MemberPlan For(ResumePlan plan, MemberSpec m) => plan.Members.Single(p => p.SpecId == m.SpecId);

    private static void AssertRefused(ResumePlan plan, PlanRefusal refusal, ExitCode exit)
    {
        Assert.True(plan.Refused);
        Assert.Equal(refusal, plan.Refusal);
        Assert.Equal(exit, plan.ExitCode);
        Assert.Empty(plan.Members);
        Assert.Empty(plan.Conflicts);
        Assert.False(string.IsNullOrEmpty(plan.Detail));
    }

    private static void AssertPlanned(ResumePlan plan)
    {
        Assert.False(plan.Refused, plan.Detail);
        Assert.Equal(PlanRefusal.None, plan.Refusal);
        Assert.False(string.IsNullOrEmpty(plan.Detail));
    }

    private static void AssertAction(ResumePlan plan, MemberSpec m, MemberAction action, Guid? guid = null)
    {
        var p = For(plan, m);
        Assert.Equal(action, p.Action);
        Assert.Equal(guid, p.Guid);
        if (action == MemberAction.Conflict)
        {
            Assert.NotEmpty(p.Conflicts);
        }
        else
        {
            Assert.Empty(p.Conflicts);
        }
    }

    /// <summary>The member is a conflict and has exactly one conflict of <paramref name="kind"/>.</summary>
    private static JournalConflict AssertMemberConflict(ResumePlan plan, MemberSpec m, ConflictKind kind, Guid? guid = null)
    {
        AssertPlanned(plan);
        Assert.Equal(ExitCode.ValidationFailure, plan.ExitCode);
        var p = For(plan, m);
        Assert.Equal(MemberAction.Conflict, p.Action);
        Assert.Null(p.Guid);
        var c = Assert.Single(p.Conflicts, x => x.Kind == kind);
        Assert.Equal(m.SpecId, c.SpecId);
        Assert.Equal(guid, c.Guid);
        Assert.False(string.IsNullOrEmpty(c.Detail));
        Assert.Contains(c, plan.Conflicts);
        return c;
    }

    private static JournalConflict AssertRunConflict(ResumePlan plan, ConflictKind kind, Guid guid, string? specId)
    {
        AssertPlanned(plan);
        Assert.Equal(ExitCode.ValidationFailure, plan.ExitCode);
        var c = Assert.Single(plan.Conflicts, x => x.Kind == kind && x.Guid == guid);
        Assert.Equal(specId, c.SpecId);
        Assert.False(string.IsNullOrEmpty(c.Detail));
        Assert.DoesNotContain(plan.Members, p => p.Conflicts.Contains(c));
        return c;
    }

    // ---- fresh run

    [Fact]
    public void No_journal_and_no_objects_creates_every_member_in_spec_order()
    {
        var plan = Plan(null);
        AssertPlanned(plan);
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
        Assert.Equal(new[] { A.SpecId, B.SpecId, C.SpecId }, plan.Members.Select(p => p.SpecId));
        Assert.All(plan.Members, p =>
        {
            Assert.Equal(MemberAction.Create, p.Action);
            Assert.Null(p.Guid);
            Assert.Empty(p.AbsentJournalObjects);
            Assert.False(p.Recreated);
            Assert.Null(p.NameNote);
        });
        Assert.Empty(plan.Conflicts);
    }

    [Fact]
    public void Untagged_object_outside_the_journal_is_ignored()
    {
        var plan = Plan(null, Obj(A, G(1)));
        AssertAction(plan, A, MemberAction.Create);
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    // ---- decision 8: crash sequences

    [Fact]
    public void Intent_still_inserting_is_a_conflict_even_if_nothing_is_visible()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, null, ObjectState.Inserting)));
        var plan = Plan(journal, Tagged(A, G(1)));
        AssertMemberConflict(plan, B, ConflictKind.IntentUnresolved, guid: null);
        AssertAction(plan, A, MemberAction.Skip, G(1));
        AssertAction(plan, C, MemberAction.Create);
    }

    [Fact]
    public void Intent_inserting_stays_a_conflict_after_a_later_entry_for_the_same_member()
    {
        var journal = Journal(Inv(JO(B, null, ObjectState.Inserting)), Inv(JO(B, G(2), ObjectState.Tagged)));
        AssertMemberConflict(Plan(journal, Tagged(B, G(2))), B, ConflictKind.IntentUnresolved);
    }

    [Fact]
    public void Inserted_and_present_untagged_is_retagged()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)));
        AssertPlanned(plan);
        AssertAction(plan, A, MemberAction.Retag, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
        Assert.Empty(For(plan, A).AbsentJournalObjects);
    }

    [Fact]
    public void Inserted_and_absent_is_recreated_and_reported()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal);
        AssertAction(plan, A, MemberAction.Create);
        var p = For(plan, A);
        Assert.True(p.Recreated);
        var absent = Assert.Single(p.AbsentJournalObjects);
        Assert.Equal(G(1), absent.Guid);
        Assert.Equal(ObjectState.Inserted, absent.LastState);
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    [Fact]
    public void Tagged_and_present_is_skipped()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)));
        AssertAction(plan, A, MemberAction.Skip, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    [Fact]
    public void Tagged_and_absent_is_recreated_with_its_last_state()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)), Inv(JO(A, G(1), ObjectState.Tagged, ObjectAction.Retagged)));
        var plan = Plan(journal);
        AssertAction(plan, A, MemberAction.Create);
        var absent = Assert.Single(For(plan, A).AbsentJournalObjects);
        Assert.Equal(ObjectState.Tagged, absent.LastState);
        Assert.True(For(plan, A).Recreated);
    }

    [Fact]
    public void The_example_journal_resumes_to_skips()
    {
        var journal = Journal(
            Inv(JO(A, G(1), ObjectState.Tagged), JO(B, G(2), ObjectState.Inserted)),
            Inv(InvocationOutcome.Ok, JournalCommand.Build, JO(B, G(2), ObjectState.Tagged, ObjectAction.Retagged), JO(C, G(3), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)), Tagged(B, G(2)), Tagged(C, G(3)));
        AssertAction(plan, A, MemberAction.Skip, G(1));
        AssertAction(plan, B, MemberAction.Skip, G(2));
        AssertAction(plan, C, MemberAction.Skip, G(3));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    [Fact]
    public void A_recreated_member_resumes_to_skip_and_keeps_listing_the_old_guid()
    {
        // inv 1 tagged g1; g1 disappeared; inv 2 recreated g2; inv 3 resumes.
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(JO(A, G(2), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(2)));
        AssertAction(plan, A, MemberAction.Skip, G(2));
        Assert.False(For(plan, A).Recreated);
        Assert.Equal(G(1), Assert.Single(For(plan, A).AbsentJournalObjects).Guid);
    }

    [Fact]
    public void An_older_journal_guid_present_while_the_latest_is_absent_is_a_conflict()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(JO(A, G(2), ObjectState.Tagged)));
        AssertMemberConflict(Plan(journal, Tagged(A, G(1))), A, ConflictKind.TagContradiction, G(1));
    }

    [Fact]
    public void Two_present_journal_guids_for_one_member_are_a_duplicate()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)), Inv(JO(A, G(2), ObjectState.Inserted)));
        AssertMemberConflict(Plan(journal, Obj(A, G(1)), Obj(A, G(2))), A, ConflictKind.DuplicateSpecId);
    }

    // ---- decision 8: partial and contradicting tags

    [Theory]
    [InlineData(LotText, null, null)]
    [InlineData(LotText, Run, null)]
    [InlineData(null, null, "L1-C-A1")]
    [InlineData(LotText, null, "L1-C-A1")]
    [InlineData(null, Run, "L1-C-A1")]
    public void Journal_object_with_missing_tags_and_none_contradicting_is_retagged(string? lot, string? run, string? specId)
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)).Tags(lot, run, specId));
        AssertAction(plan, A, MemberAction.Retag, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    [Fact]
    public void Journal_object_fully_tagged_but_recorded_as_inserted_is_skipped()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        AssertAction(Plan(journal, Tagged(A, G(1))), A, MemberAction.Skip, G(1));
    }

    [Theory]
    [InlineData("2", Run, "L1-C-A1")]
    [InlineData("01", Run, "L1-C-A1")]
    [InlineData(LotText, "R-OTHER", "L1-C-A1")]
    [InlineData(null, "R-OTHER", null)]
    [InlineData(LotText, Run, "L1-C-A9")]
    [InlineData(null, null, "l1-c-a1")]
    public void Journal_object_with_a_contradicting_tag_is_a_conflict(string? lot, string? run, string? specId)
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)).Tags(lot, run, specId));
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(1));
        Assert.DoesNotContain(plan.Members, p => p.Guid == G(1));
    }

    [Fact]
    public void Journal_object_carrying_another_members_spec_id_blocks_both_members()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)).Tags(LotText, Run, B.SpecId));
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(1));
        AssertMemberConflict(plan, B, ConflictKind.TagContradiction, G(1));
        AssertAction(plan, C, MemberAction.Create);
    }

    [Fact]
    public void One_guid_recorded_for_two_members_is_a_contradiction_not_two_retags()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted), JO(B, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)));
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(1));
        AssertMemberConflict(plan, B, ConflictKind.TagContradiction, G(1));
        Assert.DoesNotContain(plan.Members, p => p.Action == MemberAction.Retag);
    }

    [Fact]
    public void Tagged_object_that_is_not_the_journal_guid_is_a_contradiction()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(2)));
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(2));
    }

    [Fact]
    public void Journal_object_plus_another_tagged_object_is_a_duplicate()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)), Tagged(A, G(2)));
        AssertMemberConflict(plan, A, ConflictKind.DuplicateSpecId);
        Assert.DoesNotContain(plan.Members, p => p.Action == MemberAction.Retag);
    }

    // ---- decision 8: duplicate, other run, other lot, unknown, unclassified

    [Fact]
    public void Two_tagged_objects_with_one_spec_id_are_a_duplicate()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var c = AssertMemberConflict(Plan(journal, Tagged(A, G(1)), Tagged(A, G(2))), A, ConflictKind.DuplicateSpecId);
        Assert.Contains(G(1).ToString("D", CultureInfo.InvariantCulture), c.Detail, StringComparison.Ordinal);
        Assert.Contains(G(2).ToString("D", CultureInfo.InvariantCulture), c.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Two_tagged_objects_without_a_journal_refuse_before_planning()
    {
        AssertRefused(Plan(null, Tagged(A, G(1)), Tagged(A, G(2))), PlanRefusal.TaggedObjectsWithoutJournal, ExitCode.RefusedBySafetyRule);
    }

    [Theory]
    [InlineData(LotText)]
    [InlineData("2")]
    [InlineData(null)]
    public void Spec_id_under_another_run_is_a_conflict_in_any_lot(string? lot)
    {
        var plan = Plan(null, Obj(A, G(5)).Tags(lot, "R-OLD", A.SpecId));
        AssertMemberConflict(plan, A, ConflictKind.SpecIdInOtherRun, G(5));
        AssertAction(plan, B, MemberAction.Create);
    }

    [Fact]
    public void Spec_id_under_another_run_next_to_our_tagged_object_is_reported()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)), Obj(A, G(5)).Tags(LotText, "R-OLD", A.SpecId));
        AssertMemberConflict(plan, A, ConflictKind.SpecIdInOtherRun, G(5));
    }

    [Fact]
    public void Run_id_in_another_lot_is_a_run_level_conflict()
    {
        var plan = Plan(null, Obj(A, G(7)).Tags("2", Run, "L2-X"));
        AssertRunConflict(plan, ConflictKind.RunInOtherLot, G(7), "L2-X");
        Assert.All(plan.Members, p => Assert.Equal(MemberAction.Create, p.Action));
    }

    [Fact]
    public void Run_id_in_another_lot_with_one_of_our_spec_ids_blocks_that_member()
    {
        var plan = Plan(null, Obj(A, G(7)).Tags("2", Run, A.SpecId));
        AssertMemberConflict(plan, A, ConflictKind.RunInOtherLot, G(7));
    }

    [Fact]
    public void Unknown_spec_id_in_this_lot_and_run_is_a_run_level_conflict()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)), Obj(A, G(8)).Tags(LotText, Run, "L1-GONE"));
        AssertRunConflict(plan, ConflictKind.UnknownSpecId, G(8), "L1-GONE");
        AssertAction(plan, A, MemberAction.Skip, G(1));
        AssertAction(plan, B, MemberAction.Create);
    }

    [Fact]
    public void Journal_entry_for_a_spec_id_not_in_the_spec_is_an_unknown_spec_id()
    {
        var gone = Member("L1-GONE", "beam", new Point3(0, 0, 0), new Point3(1, 0, 0));
        var journal = Journal(Inv(JO(gone, G(9), ObjectState.Tagged)));
        var plan = Plan(journal);
        var c = AssertRunConflict(plan, ConflictKind.UnknownSpecId, G(9), "L1-GONE");
        Assert.Contains("journal", c.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Journal_intent_for_a_spec_id_not_in_the_spec_is_an_unknown_spec_id()
    {
        var gone = Member("L1-GONE", "beam", new Point3(0, 0, 0), new Point3(1, 0, 0));
        var plan = Plan(Journal(Inv(JO(gone, null, ObjectState.Inserting))));
        Assert.Equal(ExitCode.ValidationFailure, plan.ExitCode);
        var c = Assert.Single(plan.Conflicts);
        Assert.Equal(ConflictKind.UnknownSpecId, c.Kind);
        Assert.Equal("L1-GONE", c.SpecId);
        Assert.Null(c.Guid);
    }

    [Theory]
    [InlineData(LotText, null, null)]
    [InlineData(LotText, Run, null)]
    [InlineData(null, Run, null)]
    [InlineData(null, Run, "L1-GONE")]
    [InlineData(LotText, "R-OLD", "L1-OLD")]
    [InlineData(LotText, "R-OLD", null)]
    [InlineData(LotText, null, "L1-GONE")]
    public void Harness_tagged_object_no_rule_classifies_is_a_run_level_conflict(string? lot, string? run, string? specId)
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)), Obj(B, G(6)).Tags(lot, run, specId));
        AssertRunConflict(plan, ConflictKind.Unclassified, G(6), specId);
        AssertAction(plan, A, MemberAction.Skip, G(1));
        AssertAction(plan, B, MemberAction.Create);
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData(LotText, null)]
    [InlineData(null, Run)]
    public void Partially_tagged_object_outside_the_journal_blocks_its_member(string? lot, string? run)
    {
        var plan = Plan(Journal(), Obj(A, G(6)).Tags(lot, run, A.SpecId));
        AssertMemberConflict(plan, A, ConflictKind.Unclassified, G(6));
    }

    [Fact]
    public void Object_of_another_lot_and_run_without_our_spec_ids_is_unclassified()
    {
        var plan = Plan(Journal(), Obj(A, G(6)).Tags("2", "R-OLD", null));
        AssertRunConflict(plan, ConflictKind.Unclassified, G(6), null);
    }

    [Fact]
    public void Run_level_conflict_spec_id_text_is_kept_printable()
    {
        var plan = Plan(Journal(), Obj(A, G(6)).Tags(LotText, Run, "BAD\u0000\ud800ID"));
        var c = AssertRunConflict(plan, ConflictKind.UnknownSpecId, G(6), "BAD\\u0000\\ud800ID");
        Assert.DoesNotContain('\u0000', c.Detail);
    }

    [Fact]
    public void All_conflicts_are_returned_together()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, null, ObjectState.Inserting)));
        var plan = Plan(
            journal,
            Tagged(A, G(1)).With(o => o.Profile = "HEA320"),
            Tagged(C, G(3)),
            Tagged(C, G(4)),
            Obj(A, G(7)).Tags("2", Run, "L2-X"),
            Obj(A, G(8)).Tags(LotText, Run, "L1-GONE"));
        Assert.Equal(ExitCode.ValidationFailure, plan.ExitCode);
        Assert.Equal(
            new[] { ConflictKind.Mismatch, ConflictKind.IntentUnresolved, ConflictKind.DuplicateSpecId, ConflictKind.RunInOtherLot, ConflictKind.UnknownSpecId },
            plan.Conflicts.Select(c => c.Kind));
        Assert.All(plan.Members, p => Assert.Equal(MemberAction.Conflict, p.Action));
    }

    // ---- decision 7: what "matches" means

    [Fact]
    public void Exact_object_matches_without_a_name_note()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)));
        AssertAction(plan, A, MemberAction.Skip, G(1));
        Assert.Null(For(plan, A).NameNote);
    }

    private static ResumePlan PlanOne(MemberSpec m, Action<PlanFixtures.ObjectBuilder> change)
    {
        var journal = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
        return Plan(Spec(m), journal, Snap(journal, Tagged(m, G(1)).With(change)));
    }

    private static void AssertMatches(MemberSpec m, Action<PlanFixtures.ObjectBuilder> change)
    {
        var plan = PlanOne(m, change);
        AssertAction(plan, m, MemberAction.Skip, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    private static JournalConflict AssertMismatch(MemberSpec m, Action<PlanFixtures.ObjectBuilder> change, string field)
    {
        var c = AssertMemberConflict(PlanOne(m, change), m, ConflictKind.Mismatch, G(1));
        Assert.Contains(field, c.Detail, StringComparison.Ordinal);
        return c;
    }

    private static double NextUp(double x) => BitConverter.Int64BitsToDouble(BitConverter.DoubleToInt64Bits(x) + 1);

    [Fact]
    public void Point_exactly_0_1_mm_away_matches()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(0, 0, 0));
        AssertMatches(m, o => o.Start = new Point3(0.1, 0, 0));
        AssertMatches(m, o => o.Start = new Point3(0, -0.1, 0));
        AssertMatches(m, o => o.End = new Point3(0, 0, 0.1));
    }

    [Fact]
    public void Point_beyond_0_1_mm_plus_the_rounding_allowance_differs()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(0, 0, 0));
        var limit = ResumePlanner.PointToleranceMm + ResumePlanner.PointRoundingAllowanceMm;
        AssertMatches(m, o => o.Start = new Point3(limit, 0, 0));
        AssertMatches(m, o => o.Start = new Point3(NextUp(0.1), 0, 0));
        AssertMismatch(m, o => o.Start = new Point3(NextUp(limit), 0, 0), "start");
        AssertMismatch(m, o => o.Start = new Point3(0.1 + 2e-6, 0, 0), "start");
        AssertMismatch(m, o => o.End = new Point3(0, 0, -(0.1 + 2e-6)), "end");
    }

    [Fact]
    public void Rounding_allowance_is_one_nanometre_scale_constant()
    {
        Assert.Equal(0.1, ResumePlanner.PointToleranceMm);
        Assert.Equal(1e-6, ResumePlanner.PointRoundingAllowanceMm);
    }

    [Theory]
    [InlineData(6000.0, 6000.1)]
    [InlineData(6000.1, 6000.0)]
    [InlineData(123456.7, 123456.8)]
    [InlineData(-123456.8, -123456.7)]
    [InlineData(999999.9, 1000000.0)]
    public void Decimal_coordinates_0_1_mm_apart_match_whatever_their_size(double spec, double model)
    {
        var m = Member("M", "beam", new Point3(spec, spec, spec), new Point3(0, 0, 0));
        AssertMatches(m, o => o.Start = new Point3(model, spec, spec));
        AssertMatches(m, o => o.Start = new Point3(spec, spec, model));
    }

    [Fact]
    public void Decimal_coordinates_0_1_mm_and_a_hair_apart_differ()
    {
        var m = Member("M", "beam", new Point3(6000, 0, 0), new Point3(0, 0, 0));
        AssertMismatch(m, o => o.Start = new Point3(6000.100002, 0, 0), "start");
    }

    [Fact]
    public void Point_distance_is_euclidean_not_per_axis()
    {
        var m = Member("M", "beam", new Point3(100, 200, 300), new Point3(400, 200, 300));
        AssertMatches(m, o => o.End = new Point3(400.05, 200.05, 300.05));
        AssertMismatch(m, o => o.End = new Point3(400.06, 200.06, 300.06), "end");
    }

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(double.NegativeInfinity)]
    public void Non_finite_point_never_matches(double bad)
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0));
        AssertMismatch(m, o => o.Start = new Point3(bad, 0, 0), "start");
        AssertMismatch(m, o => o.Start = new Point3(0, bad, 0), "start");
        AssertMismatch(m, o => o.End = new Point3(1000, 0, bad), "end");
    }

    [Fact]
    public void Non_finite_spec_point_never_matches_an_identical_object_point()
    {
        var m = Member("M", "beam", new Point3(double.PositiveInfinity, 0, 0), new Point3(1000, 0, 0));
        AssertMismatch(m, o => o.Start = new Point3(double.PositiveInfinity, 0, 0), "start");
    }

    [Fact]
    public void Huge_point_difference_that_overflows_differs()
    {
        var m = Member("M", "beam", new Point3(-1e300, 0, 0), new Point3(1000, 0, 0));
        AssertMismatch(m, o => o.Start = new Point3(1e300, 0, 0), "start");
    }

    [Fact]
    public void Missing_point_never_matches()
    {
        AssertMismatch(A, o => o.Start = null, "start");
        AssertMismatch(A, o => o.End = null, "end");
    }

    [Fact]
    public void Reversed_member_differs()
    {
        var c = AssertMismatch(C, o => (o.Start, o.End) = (o.End, o.Start), "start");
        Assert.Contains("end", c.Detail, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("hea300", null)]
    [InlineData("HEA300 ", null)]
    [InlineData(null, null)]
    [InlineData("HEA300", "s355jr")]
    [InlineData("HEA300", null)]
    public void Profile_and_material_are_compared_ordinally(string? profile, string? material)
    {
        AssertMismatch(A, o => (o.Profile, o.Material) = (profile, material), profile == "HEA300" ? "material" : "profile");
    }

    [Theory]
    [InlineData("beam")]
    [InlineData("other")]
    [InlineData("Column")]
    public void Kind_must_equal_the_spec_type(string kind)
    {
        AssertMismatch(A, o => o.Kind = kind, "kind");
    }

    [Fact]
    public void Kind_other_matches_spec_type_other()
    {
        AssertMatches(Member("M", "other", new Point3(0, 0, 0), new Point3(1, 0, 0)), o => { });
    }

    [Theory]
    [InlineData(null, 0.0)]
    [InlineData(null, 0.01)]
    [InlineData(null, -0.01)]
    [InlineData(null, 360.0)]
    [InlineData(0.004, 359.995)]
    [InlineData(359.995, 0.004)]
    [InlineData(-90.0, 270.0)]
    [InlineData(0.0, 720.004)]
    [InlineData(0.0, -719.995)]
    [InlineData(45.0, 45.0)]
    public void Rotation_within_0_01_degree_modulo_360_matches(double? spec, double model)
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), rotation: spec);
        AssertMatches(m, o => o.Rotation = model);
    }

    [Theory]
    [InlineData(0.0, 0.01)]
    [InlineData(90.0, 90.01)]
    [InlineData(0.0, 359.99)]
    [InlineData(180.0, 179.99)]
    [InlineData(-90.0, 269.99)]
    [InlineData(12.34, 12.35)]
    public void Decimal_rotations_0_01_degree_apart_match(double spec, double model)
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), rotation: spec);
        AssertMatches(m, o => o.Rotation = model);
    }

    [Theory]
    [InlineData(null, 0.0101)]
    [InlineData(null, 359.989)]
    [InlineData(0.004, 359.993)]
    [InlineData(90.0, -90.0)]
    [InlineData(45.0, 45.02)]
    public void Rotation_beyond_0_01_degree_differs(double? spec, double model)
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), rotation: spec);
        AssertMismatch(m, o => o.Rotation = model, "rotation");
    }

    [Fact]
    public void Rotation_beyond_0_01_degree_plus_the_rounding_allowance_differs()
    {
        Assert.Equal(1e-9, ResumePlanner.RotationRoundingAllowanceDeg);
        var limit = ResumePlanner.RotationToleranceDeg + ResumePlanner.RotationRoundingAllowanceDeg;
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0));
        AssertMatches(m, o => o.Rotation = 0.01);
        AssertMatches(m, o => o.Rotation = limit);
        AssertMismatch(m, o => o.Rotation = NextUp(limit), "rotation");
        AssertMismatch(m, o => o.Rotation = 0.01 + 2e-9, "rotation");
        AssertMismatch(m, o => o.Rotation = -(0.01 + 2e-9), "rotation");
    }

    [Theory]
    [InlineData(null)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void Unreadable_or_non_finite_rotation_never_matches(double? model)
    {
        AssertMismatch(A, o => o.Rotation = model, "rotation");
    }

    [Fact]
    public void Non_finite_spec_rotation_never_matches()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), rotation: double.NaN);
        AssertMismatch(m, o => o.Rotation = double.NaN, "rotation");
    }

    [Fact]
    public void Class_is_compared_only_when_the_spec_gives_one()
    {
        AssertMatches(A, o => o.Class = "7");
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), memberClass: "3");
        AssertMatches(m, o => o.Class = "3");
        AssertMismatch(m, o => o.Class = "4", "class");
        AssertMismatch(m, o => o.Class = null, "class");
    }

    [Fact]
    public void Different_name_is_a_note_not_a_conflict()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), name: "BEAM-A");
        var plan = PlanOne(m, o => o.Name = "BEAM");
        AssertAction(plan, m, MemberAction.Skip, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
        var note = For(plan, m).NameNote;
        Assert.NotNull(note);
        Assert.Contains("BEAM-A", note, StringComparison.Ordinal);
        Assert.Null(For(PlanOne(m, o => { }), m).NameNote);
        Assert.NotNull(For(PlanOne(m, o => o.Name = null), m).NameNote);
        Assert.Null(For(PlanOne(Member("N", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0)), o => o.Name = "X"), Member("N", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0))).NameNote);
    }

    [Fact]
    public void Name_note_also_on_retag()
    {
        var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000, 0, 0), name: "BEAM-A");
        var journal = Journal(Inv(JO(m, G(1), ObjectState.Inserted)));
        var plan = Plan(Spec(m), journal, Snap(journal, Obj(m, G(1)).With(o => o.Name = "BEAM")));
        AssertAction(plan, m, MemberAction.Retag, G(1));
        Assert.NotNull(For(plan, m).NameNote);
    }

    [Fact]
    public void Mismatch_lists_every_differing_field()
    {
        var c = AssertMismatch(A, o => (o.Kind, o.Profile, o.Material, o.Rotation) = ("beam", "X", "Y", 5), "kind");
        foreach (var field in new[] { "profile", "material", "rotation" })
        {
            Assert.Contains(field, c.Detail, StringComparison.Ordinal);
        }

        Assert.DoesNotContain("start", c.Detail, StringComparison.Ordinal);
    }

    [Fact]
    public void Mismatching_journal_object_is_not_retagged()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        AssertMemberConflict(Plan(journal, Obj(A, G(1)).With(o => o.Profile = "HEA320")), A, ConflictKind.Mismatch, G(1));
    }

    // ---- decision 5: refusals before planning

    [Fact]
    public void Invalid_run_id_is_a_usage_error()
    {
        foreach (var bad in new[] { "", "r1", "R1\n", new string('R', 33) })
        {
            AssertRefused(ResumePlanner.Plan(Abc, bad, ModelPath, null, Snap(null)), PlanRefusal.RunIdInvalid, ExitCode.UsageError);
        }
    }

    [Fact]
    public void Journal_of_another_spec_refuses()
    {
        var journal = new RunJournal(Project, Lot, Run, "spec.json", new string('b', 64), ModelPath, new[] { Inv() });
        AssertRefused(Plan(Abc, journal, Snap(journal)), PlanRefusal.SpecHashMismatch, ExitCode.RefusedBySafetyRule);
    }

    [Theory]
    [InlineData("demo-other", Lot, Run)]
    [InlineData(Project, 2, Run)]
    [InlineData(Project, Lot, "R-OTHER")]
    public void Journal_header_of_another_run_refuses(string project, int lot, string run)
    {
        var journal = new RunJournal(project, lot, run, "spec.json", Sha, ModelPath, new[] { Inv() });
        AssertRefused(Plan(Abc, journal, Snap(journal)), PlanRefusal.JournalHeaderMismatch, ExitCode.RefusedBySafetyRule);
    }

    [Theory]
    [InlineData(@"C:\Models\other")]
    [InlineData(@"D:\Models\demo-copy")]
    [InlineData(@"C:\Models\demo-copy\sub")]
    [InlineData(@"relative\demo-copy")]
    [InlineData("")]
    public void Journal_of_another_model_refuses(string journalModel)
    {
        var journal = new RunJournal(Project, Lot, Run, "spec.json", Sha, journalModel, new[] { Inv() });
        AssertRefused(Plan(Abc, journal, Snap(journal)), PlanRefusal.ModelPathMismatch, ExitCode.RefusedBySafetyRule);
    }

    [Fact]
    public void Unparsable_open_model_path_refuses()
    {
        var journal = Journal(Inv());
        AssertRefused(ResumePlanner.Plan(Abc, Run, "demo-copy", journal, Snap(journal)), PlanRefusal.ModelPathMismatch, ExitCode.RefusedBySafetyRule);
    }

    [Fact]
    public void Model_path_compares_like_safety_rule_1()
    {
        var journal = new RunJournal(Project, Lot, Run, "spec.json", Sha, "c:/models/DEMO-COPY/", new[] { Inv() });
        AssertPlanned(Plan(Abc, journal, Snap(journal)));
    }

    [Fact]
    public void Completed_rollback_refuses()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(InvocationOutcome.Ok, JournalCommand.Rollback));
        AssertRefused(Plan(journal), PlanRefusal.RunRolledBack, ExitCode.RefusedBySafetyRule);
    }

    [Theory]
    [InlineData(InvocationOutcome.Running)]
    [InlineData(InvocationOutcome.Stopped)]
    [InlineData(InvocationOutcome.Conflict)]
    [InlineData(InvocationOutcome.Refused)]
    [InlineData(InvocationOutcome.Abandoned)]
    public void Any_rollback_refuses_even_a_partial_one(InvocationOutcome outcome)
    {
        // ADR-0012 amended: a resume must never rebuild what the engineer asked to delete.
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(outcome, JournalCommand.Rollback));
        AssertRefused(Plan(journal, Tagged(A, G(1))), PlanRefusal.RunRolledBack, ExitCode.RefusedBySafetyRule);
    }

    [Fact]
    public void Completed_build_or_update_does_not_refuse()
    {
        var journal = Journal(Inv(InvocationOutcome.Ok, JournalCommand.Build), Inv(InvocationOutcome.Ok, JournalCommand.Update));
        AssertPlanned(Plan(journal));
    }

    [Theory]
    [InlineData("L1-C-A1")]
    [InlineData("L1-GONE")]
    [InlineData(null)]
    public void No_journal_but_objects_tagged_with_this_lot_and_run_refuses(string? specId)
    {
        AssertRefused(Plan(null, Obj(A, G(1)).Tags(LotText, Run, specId)), PlanRefusal.TaggedObjectsWithoutJournal, ExitCode.RefusedBySafetyRule);
    }

    [Fact]
    public void Tagged_object_is_skipped_when_the_journal_has_no_guid_for_its_member()
    {
        // Decision 8 skip: "if the journal has a GUID for this SPEC_ID, it must be that object".
        var plan = Plan(Journal(), Tagged(A, G(1)));
        AssertAction(plan, A, MemberAction.Skip, G(1));
        Assert.Equal(ExitCode.Ok, plan.ExitCode);
    }

    // ---- decision 6: snapshot refusals

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public void Unreadable_tag_refuses_with_3(int which)
    {
        var o = Tagged(A, G(1)).With(b =>
        {
            switch (which)
            {
                case 0: b.Lot = TagReading.Unreadable; break;
                case 1: b.RunTag = TagReading.Unreadable; break;
                default: b.SpecTag = TagReading.Unreadable; break;
            }
        });
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        AssertRefused(Plan(journal, o), PlanRefusal.UnreadableTag, ExitCode.EnvironmentError);
    }

    [Fact]
    public void Journal_guid_lookup_error_refuses_with_4()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, G(2), ObjectState.Tagged)));
        var snapshot = Snap(journal, new[] { Tagged(A, G(1)) }, new Dictionary<Guid, GuidPresence> { [G(2)] = GuidPresence.Error });
        AssertRefused(Plan(Abc, journal, snapshot), PlanRefusal.GuidLookupError, ExitCode.TeklaApiError);
    }

    [Fact]
    public void Journal_guid_tagged_with_this_lot_but_missed_by_the_lot_lookup_refuses_with_3()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var o = Tagged(A, G(1)).With(b => b.FoundBy = SnapshotLookup.JournalGuid | SnapshotLookup.RunId | SnapshotLookup.SpecId);
        AssertRefused(Plan(journal, o), PlanRefusal.LookupUntrusted, ExitCode.EnvironmentError);
    }

    [Theory]
    [InlineData(SnapshotLookup.Lot | SnapshotLookup.SpecId)]
    [InlineData(SnapshotLookup.Lot | SnapshotLookup.RunId)]
    public void Object_missed_by_the_run_or_spec_id_lookup_refuses_with_3(SnapshotLookup found)
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        AssertRefused(Plan(journal, Tagged(A, G(1)).With(b => b.FoundBy = found | SnapshotLookup.JournalGuid)), PlanRefusal.LookupUntrusted, ExitCode.EnvironmentError);
    }

    [Fact]
    public void Spec_id_tag_outside_the_spec_need_not_be_found_by_the_spec_id_lookup()
    {
        var journal = Journal();
        var plan = Plan(journal, Obj(A, G(8)).Tags(LotText, Run, "L1-GONE").With(b => b.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId));
        AssertRunConflict(plan, ConflictKind.UnknownSpecId, G(8), "L1-GONE");
    }

    [Fact]
    public void Journal_guid_without_a_lookup_result_refuses_with_3()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var snapshot = new ModelSnapshot(new[] { Tagged(A, G(1)).Build(true) }, new Dictionary<Guid, GuidPresence>());
        AssertRefused(Plan(Abc, journal, snapshot), PlanRefusal.SnapshotIncomplete, ExitCode.EnvironmentError);
    }

    [Fact]
    public void Present_journal_guid_without_its_object_refuses_with_3()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var snapshot = Snap(journal, Array.Empty<PlanFixtures.ObjectBuilder>(), new Dictionary<Guid, GuidPresence> { [G(1)] = GuidPresence.Present });
        AssertRefused(Plan(Abc, journal, snapshot), PlanRefusal.SnapshotIncomplete, ExitCode.EnvironmentError);
    }

    [Fact]
    public void Absent_journal_guid_with_an_object_refuses_with_3()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)));
        var snapshot = Snap(journal, new[] { Tagged(A, G(1)) }, new Dictionary<Guid, GuidPresence> { [G(1)] = GuidPresence.Absent });
        AssertRefused(Plan(Abc, journal, snapshot), PlanRefusal.SnapshotIncomplete, ExitCode.EnvironmentError);
    }

    [Fact]
    public void Refusals_come_in_a_fixed_order()
    {
        var unreadable = Tagged(A, G(1)).With(b => b.Lot = TagReading.Unreadable);
        var badLookup = Tagged(B, G(2)).With(b => b.FoundBy = SnapshotLookup.JournalGuid);
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged), JO(B, G(2), ObjectState.Tagged), JO(C, G(3), ObjectState.Tagged)));
        var errors = new Dictionary<Guid, GuidPresence> { [G(3)] = GuidPresence.Error };
        ResumePlan P(RunJournal? j, params PlanFixtures.ObjectBuilder[] objects) => Plan(Abc, j, Snap(j, objects, errors));

        var wrongSpec = new RunJournal(Project, Lot, "R-OTHER", "spec.json", new string('b', 64), @"C:\other", journal.Invocations);
        Assert.Equal(PlanRefusal.RunIdInvalid, ResumePlanner.Plan(Abc, "bad", ModelPath, wrongSpec, Snap(wrongSpec)).Refusal);
        Assert.Equal(PlanRefusal.JournalHeaderMismatch, P(wrongSpec, unreadable).Refusal);
        var wrongHash = new RunJournal(Project, Lot, Run, "spec.json", new string('b', 64), @"C:\other", journal.Invocations);
        Assert.Equal(PlanRefusal.SpecHashMismatch, P(wrongHash, unreadable).Refusal);
        var wrongModel = new RunJournal(Project, Lot, Run, "spec.json", Sha, @"C:\other", journal.Invocations.Concat(new[] { Inv(InvocationOutcome.Ok, JournalCommand.Rollback) }));
        Assert.Equal(PlanRefusal.ModelPathMismatch, P(wrongModel, unreadable).Refusal);
        var rolledBack = journal.WithInvocations(wrongModel.Invocations);
        Assert.Equal(PlanRefusal.RunRolledBack, P(rolledBack, unreadable, badLookup).Refusal);
        Assert.Equal(PlanRefusal.TaggedObjectsWithoutJournal, P(null, Tagged(C, G(4)), unreadable).Refusal);
        Assert.Equal(PlanRefusal.UnreadableTag, P(journal, unreadable, badLookup).Refusal);
        Assert.Equal(PlanRefusal.GuidLookupError, P(journal, Tagged(A, G(1)), badLookup).Refusal);
        var missing = new ModelSnapshot(new[] { badLookup.Build(true) }, new Dictionary<Guid, GuidPresence> { [G(2)] = GuidPresence.Present });
        Assert.Equal(PlanRefusal.SnapshotIncomplete, Plan(Abc, journal, missing).Refusal);
        var complete = Snap(journal, Tagged(A, G(1)), badLookup);
        Assert.Equal(PlanRefusal.LookupUntrusted, Plan(Abc, journal, complete).Refusal);
    }

    [Fact]
    public void Null_arguments_throw()
    {
        Assert.Throws<ArgumentNullException>(() => ResumePlanner.Plan(null!, Run, ModelPath, null, Snap(null)));
        Assert.Throws<ArgumentNullException>(() => ResumePlanner.Plan(Abc, Run, ModelPath, null, null!));
        AssertRefused(ResumePlanner.Plan(Abc, null!, ModelPath, null, Snap(null)), PlanRefusal.RunIdInvalid, ExitCode.UsageError);
    }

    // ---- decision 4: abandoned invocations

    [Fact]
    public void Running_invocations_become_abandoned_and_nothing_else_changes()
    {
        var journal = Journal(
            Inv(InvocationOutcome.Running, JournalCommand.Build, JO(A, G(1), ObjectState.Tagged)),
            Inv(InvocationOutcome.Stopped, JournalCommand.Build),
            Inv(InvocationOutcome.Running, JournalCommand.Update));
        var marked = journal.MarkRunningAbandoned();
        Assert.Equal(
            new[] { InvocationOutcome.Abandoned, InvocationOutcome.Stopped, InvocationOutcome.Abandoned },
            marked.Invocations.Select(i => i.Outcome));
        Assert.Equal(
            new[] { InvocationOutcome.Running, InvocationOutcome.Stopped, InvocationOutcome.Running },
            journal.Invocations.Select(i => i.Outcome));
        Assert.Same(journal.Invocations[1], marked.Invocations[1]);
        Assert.Equal(JournalCommand.Update, marked.Invocations[2].Command);
        Assert.Equal(journal.Invocations[0].Objects, marked.Invocations[0].Objects);
        Assert.Equal(RunJournalFile.Serialize(journal).Length, RunJournalFile.Serialize(marked).Length + 2 * ("running".Length - "abandoned".Length));
    }

    // ---- culture

    [Theory]
    [InlineData("vi-VN")]
    [InlineData("tr-TR")]
    [InlineData("ar-SA")]
    public void Plans_do_not_depend_on_the_current_culture(string culture)
    {
        static string Describe()
        {
            var m = Member("M", "beam", new Point3(0, 0, 0), new Point3(1000.5, 0, 0), rotation: 359.995, name: "Dầm");
            var journal = Journal(Inv(JO(m, G(1), ObjectState.Tagged)));
            var lotTen = new LotSpec("0.1", Project, 1000, new[] { m }, Sha, 1);
            var tagged = Tagged(m, G(1)).With(o => (o.Rotation, o.End, o.Name) = (0.004, new Point3(1000.55, 0, 0), "dam"));
            var p1 = Plan(Spec(m), journal, Snap(journal, tagged));
            var off = Tagged(m, G(1)).With(o => (o.Rotation, o.End) = (1.5, new Point3(1000.75, 0, 0)));
            var p2 = Plan(Spec(m), journal, Snap(journal, off));
            var lotJournal = new RunJournal(Project, 1000, Run, "spec.json", Sha, ModelPath, Array.Empty<JournalInvocation>());
            var gone = Obj(m, G(2)).Tags("1000", Run, "GONE").With(o => o.FoundBy = SnapshotLookup.Lot | SnapshotLookup.RunId);
            var p3 = ResumePlanner.Plan(lotTen, Run, ModelPath, lotJournal, Snap(lotJournal, gone));
            return string.Join("|", p1.Members[0].Action, p1.Members[0].NameNote, p2.Conflicts[0].Detail, p3.Conflicts[0].Kind, p3.Members[0].Action);
        }

        var saved = Thread.CurrentThread.CurrentCulture;
        string invariant;
        try
        {
            Thread.CurrentThread.CurrentCulture = CultureInfo.InvariantCulture;
            invariant = Describe();
            Thread.CurrentThread.CurrentCulture = new CultureInfo(culture);
            Assert.Equal(invariant, Describe());
        }
        finally
        {
            Thread.CurrentThread.CurrentCulture = saved;
        }

        Assert.StartsWith("Skip|", invariant, StringComparison.Ordinal);
        Assert.Contains("1000.75", invariant, StringComparison.Ordinal);
        Assert.Contains("1.5", invariant, StringComparison.Ordinal);
        Assert.EndsWith("|UnknownSpecId|Create", invariant, StringComparison.Ordinal);
    }

    // ---- invariants over random snapshots

    [Fact]
    public void Random_snapshots_never_create_over_an_existing_member_or_target_a_guid_twice()
    {
        var random = new Random(12026);
        var lots = new[] { null, LotText, "2" };
        var runs = new[] { null, Run, "R-OLD" };
        var specIds = new[] { null, A.SpecId, B.SpecId, C.SpecId, "L1-GONE" };
        var members = new[] { A, B, C };
        var planned = 0;
        for (var round = 0; round < 3000; round++)
        {
            var entries = new List<JournalObject>();
            var objects = new List<PlanFixtures.ObjectBuilder>();
            var presence = new Dictionary<Guid, GuidPresence>();
            for (var n = 1; n <= random.Next(0, 6); n++)
            {
                var g = G(n);
                var m = members[random.Next(members.Length)];
                if (random.Next(3) == 0)
                {
                    var state = (ObjectState)random.Next(3);
                    entries.Add(JO(m, state == ObjectState.Inserting ? null : g, state));
                }

                if (random.Next(4) != 0)
                {
                    var o = Obj(m, g).Tags(lots[random.Next(3)], runs[random.Next(3)], specIds[random.Next(5)]);
                    if (random.Next(5) == 0)
                    {
                        o.Profile = "X";
                    }

                    objects.Add(o);
                }
            }

            var journal = random.Next(4) == 0 ? null : Journal(Inv(entries.ToArray()));
            if (journal is null)
            {
                entries.Clear(); // the planner never sees them
            }

            var plan = Plan(Abc, journal, Snap(journal, objects, presence));
            if (plan.Refused)
            {
                Assert.Empty(plan.Members);
                continue;
            }

            planned++;
            Assert.Equal(members.Select(m => m.SpecId), plan.Members.Select(p => p.SpecId));
            Assert.Equal(plan.Conflicts.Count > 0 ? ExitCode.ValidationFailure : ExitCode.Ok, plan.ExitCode);
            var targets = plan.Members.Where(p => p.Guid.HasValue).Select(p => p.Guid!.Value).ToList();
            Assert.Equal(targets.Count, targets.Distinct().Count());
            foreach (var p in plan.Members)
            {
                Assert.Equal(p.Action is MemberAction.Skip or MemberAction.Retag, p.Guid.HasValue);
                Assert.Equal(p.Action == MemberAction.Conflict, p.Conflicts.Count > 0);
                if (p.Action == MemberAction.Create)
                {
                    Assert.DoesNotContain(objects, o => o.SpecTag.Value == p.SpecId);
                    Assert.DoesNotContain(entries, e => e.SpecId == p.SpecId && (e.Guid is null || objects.Any(o => o.Guid == e.Guid)));
                }

                if (p.Action is MemberAction.Skip or MemberAction.Retag)
                {
                    var target = objects.Single(o => o.Guid == p.Guid);
                    var member = members.Single(m => m.SpecId == p.SpecId);
                    Assert.Equal(member.Profile, target.Profile);
                    Assert.Equal(member.Type, target.Kind);
                    Assert.Equal((member.Start.X, member.Start.Y, member.Start.Z, member.End.X, member.End.Y, member.End.Z), (target.Start!.X, target.Start.Y, target.Start.Z, target.End!.X, target.End.Y, target.End.Z));
                    Assert.True(target.SpecTag.State == TagState.Absent || target.SpecTag.Value == p.SpecId);
                    Assert.True(target.Lot.State == TagState.Absent || target.Lot.Value == LotText);
                    Assert.True(target.RunTag.State == TagState.Absent || target.RunTag.Value == Run);
                }
            }

            // Every object with a tag value is a target, named by a conflict, or tied to a member in conflict.
            var conflicted = new HashSet<string>(plan.Members.Where(p => p.Action == MemberAction.Conflict).Select(p => p.SpecId));
            foreach (var o in objects.Where(o => o.Lot.State == TagState.Value || o.RunTag.State == TagState.Value || o.SpecTag.State == TagState.Value))
            {
                var text = o.Guid.ToString("D", CultureInfo.InvariantCulture);
                Assert.True(
                    targets.Contains(o.Guid)
                    || plan.Conflicts.Any(c => c.Guid == o.Guid || c.Detail.IndexOf(text, StringComparison.Ordinal) >= 0)
                    || (o.SpecTag.Value is not null && conflicted.Contains(o.SpecTag.Value))
                    || entries.Any(e => e.Guid == o.Guid && conflicted.Contains(e.SpecId)),
                    "object " + text + " is neither planned nor accounted for by a conflict");
            }
        }

        Assert.True(planned > 1000, "too few random snapshots were planned: " + planned.ToString(CultureInfo.InvariantCulture));
    }

    // ---- edges found by mutation testing

    [Fact]
    public void Absent_guid_recorded_for_two_members_blocks_both()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted), JO(B, G(1), ObjectState.Inserted)));
        var plan = Plan(journal);
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(1));
        AssertMemberConflict(plan, B, ConflictKind.TagContradiction, G(1));
    }

    [Fact]
    public void Contradicting_journal_object_is_not_classified_again()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Inserted)));
        var plan = Plan(journal, Obj(A, G(1)).Tags(LotText, Run, "L1-GONE"));
        Assert.Equal(ConflictKind.TagContradiction, Assert.Single(plan.Conflicts).Kind);
    }

    [Fact]
    public void One_object_can_carry_several_conflict_kinds()
    {
        var journal = Journal(Inv(JO(A, G(1), ObjectState.Tagged)), Inv(JO(A, G(2), ObjectState.Tagged)));
        var plan = Plan(journal, Tagged(A, G(1)).With(o => o.Profile = "HEA320"));
        AssertMemberConflict(plan, A, ConflictKind.TagContradiction, G(1));
        AssertMemberConflict(plan, A, ConflictKind.Mismatch, G(1));
    }

    [Fact]
    public void Run_level_conflicts_are_deduplicated_per_kind_spec_id_and_guid()
    {
        var gone = Member("L1-GONE", "beam", new Point3(0, 0, 0), new Point3(1, 0, 0));
        var other = Member("L1-OTHER", "beam", new Point3(0, 0, 0), new Point3(1, 0, 0));
        var journal = Journal(
            Inv(JO(gone, G(9), ObjectState.Inserted), JO(gone, null, ObjectState.Inserting), JO(other, null, ObjectState.Inserting)),
            Inv(JO(gone, G(9), ObjectState.Tagged, ObjectAction.Retagged)));
        var plan = Plan(journal);
        Assert.Equal(
            new[] { ("L1-GONE", (Guid?)G(9)), ("L1-GONE", null), ("L1-OTHER", null) },
            plan.Conflicts.Select(c => (c.SpecId!, c.Guid)));
        Assert.All(plan.Conflicts, c => Assert.Equal(ConflictKind.UnknownSpecId, c.Kind));
    }

    [Fact]
    public void Printable_keeps_pairs_and_spaces_and_escapes_the_rest()
    {
        var tag = "BAD\u0000 " + "😀" + new string('\ud800', 1) + "ID" + new string('\ud83d', 1);
        var plan = Plan(Journal(), Obj(A, G(6)).Tags(LotText, Run, tag));
        AssertRunConflict(plan, ConflictKind.UnknownSpecId, G(6), "BAD\\u0000 😀\\ud800ID\\ud83d");
        var low = Plan(Journal(), Obj(A, G(6)).Tags(LotText, Run, "X" + new string('\ude00', 1) + "\u001f"));
        AssertRunConflict(low, ConflictKind.UnknownSpecId, G(6), "X\\ude00\\u001f");
    }

    [Fact]
    public void Tag_value_must_be_non_empty()
    {
        Assert.StartsWith("A tag value is non-empty", Assert.Throws<ArgumentException>(() => TagReading.Of(string.Empty)).Message, StringComparison.Ordinal);
        Assert.Throws<ArgumentException>(() => TagReading.Of(null!));
        Assert.Equal("X", TagReading.Of("X").Value);
        Assert.Equal(TagState.Value, TagReading.Of("X").State);
        Assert.Null(TagReading.Absent.Value);
        Assert.Equal(TagState.Unreadable, TagReading.Unreadable.State);
    }

    [Fact]
    public void Snapshot_refuses_one_guid_twice()
    {
        var e = Assert.Throws<ArgumentException>(() => Snap(null, Obj(A, G(1)), Obj(B, G(1))));
        Assert.StartsWith("Object " + G(1).ToString("D", CultureInfo.InvariantCulture) + " appears twice.", e.Message, StringComparison.Ordinal);
        Assert.Equal(2, Snap(null, Obj(A, G(1)), Obj(B, G(2))).Objects.Count);
        Assert.Throws<ArgumentNullException>(() => new ModelSnapshot(Array.Empty<SnapshotObject>(), null!));
    }
}
