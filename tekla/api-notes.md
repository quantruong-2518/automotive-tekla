# Tekla Open API notes (Step 3 input)

Purpose: everything needed to start `TeklaCore` + the console CLI against **Tekla Structures 2024 (Diamond)**, with the 2025/2026 deltas.
Under review (engineer, 2026-11-09): the company runs Tekla **2026** Diamond; the target is confirmed when Step 3 resumes after Steps 1–2 ([roadmap](../docs/roadmap.md), Step 3). The 2026 deltas below were not researched in depth.
Date accessed: **2026-11-06**. Authored by a research agent on a Linux machine with no Tekla installed.

**Status of these notes: doc-sourced, NOT run-verified.** Nothing here was executed against Tekla. Every claim carries a status:
`doc` = Trimble web docs (fetched page) · `nuget-metadata` = read from the NuGet packages themselves (nuspec, DLL metadata, shipped XML docs) · `sample-code` = Trimble GitHub samples · `secondary` = non-Trimble · `not-found` = looked, no primary source.
Claim format: claim · applies to · source · status.
Review (2026-11-06, orchestrator): re-checked against the NuGet packages: the version list, 2024 `net48` + `netstandard2.0` vs 2026 `netstandard2.0`-only for Model, no public SaveAs on `ModelHandler`, no `Column` class, IFC4-only export API in 2024. All matched.

Abbreviations for sources:
- **PKG24** = `Tekla.Structures.Model` / `Tekla.Structures` / `Tekla.Structures.Catalogs` **2024.0.4** `.nupkg` from `https://api.nuget.org/v3-flatcontainer/<id>/2024.0.4/` (shipped XML doc `lib/net48/*.xml`, member IDs quoted as `M:`/`P:`).
- **PKG25** / **PKG26** = same for `Tekla.Structures.Model` 2025.0.0 / 2026.0.3.
- **GACLESS** = https://developer.tekla.com/documentation/gacless-tekla-structures-2024-developer-impact
- **REL24 / REL25 / REL26** = https://developer.tekla.com/documentation/tekla-structures-{2024,2025,2026}-open-api-release-notes
- **SAMPLES** = https://github.com/TrimbleSolutionsCorporation/TSOpenAPIExamples (branches `2024`, `2025`, `2026`; BSD-3-Clause)

---

## Summary for Step 3

### Headline: places where the API does NOT match `docs/tekla-cli-contract.md`

1. **Rollback (rule 5, "on any API error, roll back").** There is **no transaction, undo or rollback method** in the Open API. `Model.CommitChanges()` only creates one user-undoable step and redraws; `Events.UndoClicked` is an event, not a call. (PKG24 `M:...Model.CommitChanges`, `E:...Events.UndoClicked` · all · `nuget-metadata`). "Roll back" therefore has to be implemented by `TeklaCore`: track the `Identifier`/GUID of every created object and `Delete()` them, or restore the lot backup. Objects modified (not created) by `update` can only be restored from a stored before-image of their properties or from the backup. Do uncommitted inserts persist after an error? Unknown (see To verify).
2. **Backup (rule 2, "backup for this lot exists or is created first").** `ModelHandler` has only `Close, CreateNewSingleUserModel, CreateNewMultiUserModel, IsModelAutoSaved, IsModelSaved, Open, Save(2 overloads)`. **No SaveAs / backup method in 2024, 2025 or 2026**; `Operation.SaveAsWebModel` is a web viewer export, not a backup. (PKG24/PKG26 XML; https://developer.tekla.com/doc/tekla-structures/2026/model-handler-class-71964 · all · `nuget-metadata` + `doc`). The UI has *File > Save as > Save and create backup copy* (keeps GUIDs; plain *Save as* changes all GUIDs and "can't serve as a backup") (https://support.tekla.com/doc/tekla-structures/2024/mod_saving_model_with_different_name_or_location · 2024 · `doc`). **Engineer decision**: (a) run that UI command through a Tekla macro from the API (`Operation.RunMacro`; macro content/availability not verified), or (b) `ModelHandler.Save(...)` then copy the model folder with file operations (our inference, unverified; the open model holds files). Option (b) variant: require the engineer to take the backup in the UI and have the CLI only check that one exists.
3. **exe.config / assembly binding (biggest Step 3 blocker).** Since 2024 Tekla assemblies are not in the GAC. A stand-alone exe finds them only through a patched `<exe>.config` (`codeBase` + `bindingRedirect 0.0.0.0-2099.1.0.0 -> 2024.0.0.0`). Tekla patches automatically only exes placed under its extension/firm/project/macro folders at Tekla start-up. An exe anywhere else is not patched. (GACLESS · 2024+ · `doc`). Trimble's own recommendation is to patch in **Debug builds only**. **Engineer decision**: either (A) keep the CLI outside Tekla folders and make the build patch it in Release too (set `TeklaVersion` unconditionally with `TSAppConfigPatcherTask`; the patched config hard-codes the Tekla `bin` path), or (B) deploy `tekla-cli.exe` into a sub-folder of `XS_EXTENSION_DIRECTORY` (e.g. `C:\ProgramData\Trimble\Tekla Structures\2024.0\Environments\common\extensions\TeklaCli\`) and let Tekla patch it at start-up. Recommendation: **A for development, B for the Tekla machine**, then verify (To verify #1).
4. **`export` is not purely read.** `CreateReportFromSelected` and `CreateIFC4ExportFromSelected` work on the **UI selection**, so the CLI must set the selection (`Tekla.Structures.Model.UI.ModelObjectSelector.Select`), export, then restore the previous selection. `CreateReportFromAll`/`CreateIFC4ExportFromAll` ignore the selection but cannot filter by lot. Reports need a `.rpt` template in the model folder or `XS_TEMPLATE_DIRECTORY`; output goes to `XS_REPORT_OUTPUT_DIRECTORY` unless a path is given; the folder must exist. `CreateReportFromAll` is documented as **asynchronous** (output file may not exist yet). **2024 has IFC4 export as an API call; IFC2x3 is an API call only from 2026** (`CreateIFC2x3Export`); in 2024 IFC2x3 needs a macro/UI. CSV can instead be produced deterministically in code from `GetReportProperty`. (PKG24/PKG26 XML · `nuget-metadata`)
5. **Multiple Tekla sessions.** External apps "still communicate only with the first session started". So rule 1 (open model path must equal the declared working copy) is the real guard against writing to the wrong model; check it on **every** command. (https://support.tekla.com/node/137102?old_alias_match=1 · 2019 SP7+/2020 SP1+ statement; no date shown · `doc`)
6. **UDA safety.** (a) `CatalogHandler.GetUserPropertyItems()` enumerates defined UDAs, so `info`/`validate` can refuse to run when `LOT`, `RUN_ID`, `SPEC_ID` are not defined (`nuget-metadata`). (b) In `objects.inp`, plain `attribute` values are **copied with the part** when an engineer copies it in the UI; `unique_attribute` is never copied (https://support.tekla.com/doc/tekla-structures/2024/sys_objects_inp_properties · `doc`). A copied part that inherits `RUN_ID` would be deleted by a later `rollback`. Recommend `unique_attribute` for all three, `special_flag no` (so they do not affect numbering). **Engineer decision** (and company `objects.inp` ownership).
7. **Headless is probably not available.** Trimble's headless sample README: "Currently on Flex is supported. Start TS with flex, close TS and Headless applications can be run." The sample cannot run under a debugger. (https://github.com/TrimbleSolutionsCorporation/HeadlessTeklaStructuresExample · 2021/2026 projects · `sample-code`). The company uses a Diamond subscription; assume the CLI needs a **running, licensed Tekla UI session** (as ADR 0002 already assumes) until a licence owner says otherwise.

### No contradiction found
- **.NET Framework 4.8 is correct for 2024, 2025 and 2026.** 2024: "Tekla Structures and Tekla Open API are now built using .NET Framework 4.8"; .NET 6/7/8 "not yet supported to compile tools" (REL24 · `doc`). System requirements for 2024, 2025, 2026 list "Microsoft .NET Framework 4.8" and no modern .NET (https://support.tekla.com/doc/tekla-structures/2024/ins_tekla_structures_hardware_recommendations, `.../2025/...`, `.../2026/...` · `doc`). Trimble's 2026 samples still target `net48`, `x64` (SAMPLES branch `2026`, `HeadlessTeklaStructuresExample/HeadlessExample.2026.csproj` · `sample-code`). README's "NuGet exact version TBD": see below, use **2024.0.4**.
- "Tekla version + SP decides the NuGet version" (contract, Open questions): only partially true. NuGet has just 2024.0.0 to 2024.0.4; every 2024.0.x DLL has AssemblyVersion `2024.0.0.0`; the mapping NuGet patch -> Tekla service pack is **not documented** (Gaps). Use the highest 2024.x ("select the uppermost one", https://developer.tekla.com/documentation/install-tekla-open-api-and-add-assemblies-references · `doc`) and read the real Tekla build with `TeklaStructuresInfo` at run time.

### Decisions the engineer must make
**Decided 2026-11-07 in [ADR-0007](../docs/decisions/0007-tekla-cli-failure-backup-and-tags.md):** items 1–3 (config at build time; backup by macro; per-model `objects.inp` with `unique_attribute`), plus failure handling (stop, keep, resume by `SPEC_ID`; no automatic delete) and the guard fix (RTI-0006). Items 4–6 remain open.

1. exe.config strategy (A/B above).
2. Backup method (macro vs `Save` + folder copy vs engineer-made).
3. UDA definition: who adds `LOT`, `RUN_ID`, `SPEC_ID` to the company `objects.inp` (model/project/firm folder, not the global file), `unique_attribute`, and `special_flag no`.
4. Confirm the licence is a Diamond *subscription* and whether a second Tekla session / headless is ever wanted.
5. EULA/Partner question if the CLI is ever given to a third party (section 4).
6. Confirm the exact 2024 service pack installed (for the version report only).

### Start-here checklist
1. Create `Directory.Build.props` + `TeklaCli.csproj` from section 1 (net48, x64, `Tekla.Structures.Model` 2024.0.4, `Tekla.Structures.Catalogs` 2024.0.4, `TSAppConfigPatcherTask` 2.1.3).
2. Build; confirm the output is named `tekla-cli.exe` (never run it via `dotnet run`: the guard cannot see that) and `bin\...\tekla-cli.exe.config` contains `codeBase` lines pointing at `...\Tekla Structures\2024.0\bin`.
3. First connection test (Tekla 2024 running, empty test model open): `new Model().GetConnectionStatus()`, `GetInfo().ModelPath`, `TeklaStructuresInfo.GetCurrentProgramVersion()`; also run with Tekla closed and record whether it throws or returns false (To verify #2).
4. First catalog test: `GetUserPropertyItems()` lists `LOT`/`RUN_ID`/`SPEC_ID`; `MaterialItem.Select("S235JR")`; `LibraryProfileItem.Select("HEA400")`.
5. First build test on the *test model copy*: `new Beam(Beam.BeamTypeEnum.COLUMN)`, set profile/material, `Insert()`, `SetUserProperty` x3, `Modify()`, `Model.CommitChanges("...")`; then query back by UDA filter and GUID; then delete by Identifier and commit.
6. Record each result in this file (change status to `run-verified` with Tekla build number).

---

## 1. Packages for 2024

- **Package IDs (all by Trimble, nuget.org, EULA file license, `requireLicenseAcceptance=true`)**: `Tekla.Structures.Model` (Model API; pulls `Tekla.Structures` + `Tekla.Structures.Datatype`), `Tekla.Structures.Catalogs` (pulls Model + `Tekla.Structures` + Datatype), `Tekla.Structures.Drawing`, `Tekla.Structures.Plugins`, `Tekla.Structures.Dialog`, `Tekla.Structures.Analysis`, `Tekla.Structures.CustomPropertyPlugin`, `Tekla.Structures.Service` (headless host, see 2), `Tekla.Structures.Datatype`, `Tekla.Structures` (shared types: `Identifier`, `TeklaStructuresInfo`, `TeklaStructuresSettings`, filter expressions, `Geometry3d`). `Tekla.Structures.All` (embedded DLLs) exists but its 2024 versions stop at 2024.0.1. `TeklaOpenAPI` 2021.0.1 is deprecated. · all · https://azuresearch-usnc.nuget.org/query?q=Tekla.Structures&take=100 (first 37 of 49 hits read) · `nuget-metadata`
- **Needed for the 8 subcommands**: `Tekla.Structures.Model` + `Tekla.Structures.Catalogs` only (Datatype and `Tekla.Structures` arrive transitively). Not needed: Drawing, Plugins, Dialog, Analysis. · 2024 · PKG24 nuspecs · `nuget-metadata`
- **Versions of `Tekla.Structures.Model`** (publish dates from the NuGet page): 2024.0.0 (2024-02-14), 2024.0.1 (2024-04-08), 2024.0.2 (2024-04-17), 2024.0.3 (2024-10-30), 2024.0.4 (2024-11-05); 2025.0.0-beta001 (2025-01-27), 2025.0.0 (2025-02-12); 2026.0.0 (2026-02-11), 2026.0.2 (2026-04-02), 2026.0.3 (2026-04-03). `Tekla.Structures.Catalogs` and `.Drawing` have the identical version list. · all · https://www.nuget.org/packages/Tekla.Structures.Model · `nuget-metadata`
- **Which 2024.0.x matches which 2024 SP**: not documented anywhere found. Tekla 2024 has SP1..SP13 (as of 2026-10-15) but the release-notes summary has no build numbers and NuGet stops at 2024.0.4 (2024-11-05). Do not infer a mapping. · 2024 · https://support.tekla.com/doc/tekla-structures/not-version-specific/release_notes_summary_across_tekla_structures_versions (first 100k chars read) · `not-found`
- **Assembly identity**: every 2024.0.x DLL I inspected (Model, `Tekla.Structures`, Catalogs 2024.0.4) has AssemblyVersion **2024.0.0.0**. The runtime binds through the patched redirect, so the NuGet patch level only matters at compile time. · 2024 · PKG24 DLL metadata · `nuget-metadata`
- **Target framework declared**: 2024 and 2025 packages ship `lib/net48/` **and** `lib/netstandard2.0/`; dependency groups `.NETFramework4.8` and `.NETStandard2.0` (same deps). **2026 `Tekla.Structures.Model` ships `lib/netstandard2.0/` only** (`Tekla.Structures` 2026 still ships both). · 2024/2025/2026 · nuspecs + package file listings · `nuget-metadata`
- **2024.0.4 dependencies of Model**: Datatype 2024.0.4, `Tekla.Structures` 2024.0.4, Tekla.Common.Geometry 4.6.2, Tekla.Technology.Serialization 4.1.1, Trimble.Remoting 1.0.2. Catalogs adds Model. · 2024 · PKG24 nuspec · `nuget-metadata`
- **Platform**: 2024 and 2025 DLLs are managed AnyCPU (PE32, ILONLY, no 32BITREQUIRED, no 32BITPREFERRED); **2026 DLLs are x64-only (PE32+ AMD64)**. Tekla 2024+ itself requires 64-bit Windows. Product bulletin: "only x64 Tekla Open API extensions will be supported" from 2026 (summary only; full text behind login). Trimble's 2025 and 2026 samples set `<PlatformTarget>x64</PlatformTarget>` (the 2024 samples do not). **Recommendation: set x64 now** so the same project file works for 2026. · 2024/2025/2026 · PKG24/25/26 DLL headers; https://support.tekla.com/bulletin/product-bulletin-important-change-for-tekla-open-api-extensions-in-tekla-structures-2026 · `nuget-metadata` / `doc` (bulletin summary only) / `sample-code`
- **csproj style**: SDK-style (`Microsoft.NET.Sdk`, `TargetFramework net48`) is what Trimble's own 2024-2026 samples use, and it works with the declared framework (`net48`). No Trimble sample uses an old-style csproj; use SDK-style. · 2024 · SAMPLES branch `2024` `Model/Applications/BeamApplication/BeamApplication.csproj` · `sample-code`
- **Ready-to-paste (2024)**:
  ```xml
  <!-- Directory.Build.props (keep next to the solution; do not set both properties) -->
  <Project>
    <PropertyGroup>
      <!-- Trimble's sample sets this only for Debug; unconditional here so Release also gets a patched exe.config -->
      <TeklaVersion>2024.0</TeklaVersion>
      <!-- alternative: <TeklaStructuresInstallationPath>C:\Program Files\Tekla Structures\2024.0\bin</TeklaStructuresInstallationPath> -->
    </PropertyGroup>
  </Project>
  ```
  ```xml
  <!-- TeklaCli.csproj -->
  <Project Sdk="Microsoft.NET.Sdk">
    <PropertyGroup>
      <OutputType>Exe</OutputType>
      <!-- Required: the write guard only recognises the executable name tekla-cli(.exe).
           The SDK default would be TeklaCli.exe, which the guard does not see (RTI-0006). -->
      <AssemblyName>tekla-cli</AssemblyName>
      <RootNamespace>TeklaCli</RootNamespace>
      <TargetFramework>net48</TargetFramework>
      <PlatformTarget>x64</PlatformTarget>
    </PropertyGroup>
    <ItemGroup>
      <PackageReference Include="Tekla.Structures.Model" Version="2024.0.4" />
      <PackageReference Include="Tekla.Structures.Catalogs" Version="2024.0.4" />
      <PackageReference Include="TSAppConfigPatcherTask" Version="2.1.3" />
    </ItemGroup>
  </Project>
  ```
  Trimble's 2024 sample uses exactly `Tekla.Structures.Model 2024.0.4` + `TSAppConfigPatcherTask 2.1.3` (`Directory.Build.Props` there: `<TeklaVersion Condition="'$(Configuration)' == 'Debug'">2024.0</TeklaVersion>`). GACLESS says `TSAppConfigPatcherTask` **2.1.0 or later**; 2.1.3 is the latest on NuGet (2024-04-01). · 2024 · SAMPLES branch `2024`; GACLESS; api.nuget.org flat container · `sample-code` / `doc`
- **What `TSAppConfigPatcherTask` does** (package 2.1.3 `build/TSAppConfigPatcherTask.targets`): after build, for outputs that are `.exe`, `*Test.dll` or `*Tests.dll` (or `ForceApplyAppConfig=true`), and when `TeklaVersion`, `TeklaStructuresInstallationPath` or `SourceAppConfigExe` is set, writes `obj\...\App.config` with `codeBase` entries for the "GAC dll" list (Tekla.Structures*.dll, Tekla.Common.Geometry*.dll, Tekla.Technology.Serialization.dll, Trimble.Remoting.dll, Grpc*, ...). Opt-out: `DisablePatchCodeBaseToAppConfigFiles=true`. · 2024+ · package contents · `nuget-metadata`
- **Full `GacDlls` list of the patcher** (same targets file, read 2026-11-07 from the api.nuget.org flat container): `@(UserDefinedGacDlls)`, `DotNetKit`, `Tekla.Logging`, `Tekla.Application.Library`, `Tekla.Structures.*` (WebBrowser, WorkspaceApiConnector, base, Datatype, Dialog, Drawing, Model, Plugins, Analysis, Catalogs, Ui.WpfKit, CustomPropertyPlugin, Geometry3d.Compatibility, DrawingPresentationPluginInterface, DrawingPresentationModel, ObjectDimensioningPlugin, ObjectDimensioningModel, Dialog.Data, DirectManipulation), `Tekla.BIM.*` (Geometry, Common.Contracts, Utilities, DirectManipulation), `Model.Common`, `Akit5`, `Tekla.Technology.Scripting(.Plugins)`, `Trimble.Technology.Rkit`, `Trimble.Technology.MsgLib`, `Tekla.Technology.Serialization`, `Tekla.Common.Geometry(.Primitives, .Shapes)`, `Trimble.Remoting`, `Trimble.Package.Manager`, **`System.Runtime.CompilerServices.Unsafe`**, `Grpc.Core.Api`, `Grpc.Core`, `Grpc.Net.Client`, `Grpc.Net.Common`, `Google.Protobuf`. Each listed DLL gets a codeBase into Tekla's `bin` and the wide redirect, so Tekla picks its version at run time. Consequence: no dependency of our .NET projects may pull one of these (`System.Text.Json` on netstandard2.0 depends on `System.Runtime.CompilerServices.Unsafe`); ADR-0010 Amendment 1 therefore uses a hand-written JSON reader. Not on the list: `Newtonsoft.Json`, `System.Text.Json`, `System.Memory`, `System.Buffers`. · 2024+ · package contents · `nuget-metadata`
- **Do not copy Tekla DLLs by hand.** Use NuGet only for compile-time; the exe resolves via the patched config. GACLESS: "Tekla Structures will still be able to load the version deployed with the extension" (ambiguous for stand-alone exes) and "Don't deploy GAC assemblies". Copy Local / `ExcludeAssets` behaviour is not documented. · 2024 · GACLESS · `doc` + `not-found`
- Expect **MSB3277** version-conflict warnings for `Tekla.Structures.Model` when patching; Trimble calls them development-only. · 2024 · GACLESS · `doc`

## 2. Connecting an external .exe to a running Tekla

- **Required call sequence**: `Model m = new Model(); if (!m.GetConnectionStatus()) {...}`. Trimble: applications "don't start with Tekla Structures, so they can't assume it's running"; `GetConnectionStatus()` is "one way of checking if the Tekla Structures is running and a model is open". · 2024 · https://developer.tekla.com/documentation/check-connection-between-application-and-tekla-structures · `doc`
- `Model()` "creates a handle to the currently open model". `GetConnectionStatus()` "returns true if a proper connection to the Tekla Structures process has been established. Currently, there's no way to re-establish the connection." So on `false`, exit (code 3) and let the caller restart; do not retry in-process. Same text on `CatalogHandler.GetConnectionStatus`. · all · PKG24 `M:Tekla.Structures.Model.Model.#ctor`, `M:...Model.GetConnectionStatus`, `M:Tekla.Structures.Catalogs.CatalogHandler.GetConnectionStatus`; https://developer.tekla.com/doc/tekla-structures/2026/model-class-71942 · `nuget-metadata` + `doc`
- **No model open**: `ModelInfo.ModelName.Length == 0` means no model is open while connected (shipped example). · 2024 · PKG24 `T:Tekla.Structures.Model.ModelInfo` · `nuget-metadata`
- **Trimble's own samples guard with try/catch around `new Model().GetInfo()`** and report "Tekla Structures not running" on exception, i.e. do not assume `GetConnectionStatus()==false` is the only failure mode. · 2021-2026 · `MultiTeklaStructuresMonitor/TeklaGrpcApiService/Services/TeklaGrpcApiService.cs` · `sample-code`
- **Same major version**: "code written with Tekla Open API 2024 ... will connect with Tekla Structures 2024"; this is achieved through the patched `exe.config` (codeBase to the 2024 `bin`, `bindingRedirect 0.0.0.0-2099.1.0.0 -> 2024.0.0.0`). · 2024 · check-connection page + GACLESS · `doc`
- **Bitness**: Tekla 2024+ is 64-bit only; DLLs are AnyCPU (2024/2025) or x64 (2026). Run the CLI as 64-bit. (section 1)
- **Multiple running instances**: external apps "still communicate only with the first session started" (since TTSD-34070 apps *launched from inside Tekla* can use multiple sessions). Which of several same-version sessions `new Model()` binds to is not documented beyond that sentence. For different *versions*, Trimble's sample runs one driver exe per installed version, each with its own patched config. · 2020 SP1+ · https://support.tekla.com/node/137102?old_alias_match=1 ; https://github.com/TrimbleSolutionsCorporation/MultiTeklaStructuresMonitor · `doc` / `sample-code`
- **Same user / elevation / what happens on mismatch (wrong version, different user, elevated vs non-elevated)**: no primary source found. Not filled from general knowledge. · all · `not-found` (Gaps; To verify #3)
- **Where the exe lives**: placed under a Tekla extension/firm/project/macro folder it is patched automatically at Tekla start-up; elsewhere it is not patched; a macro can patch it first with `DotNetKit.AppConfigHelpers.NormalizeAppConfigForApplicationExe(exePath)` (needs write access to the exe folder; not for `C:\Program Files`). Trimble recommends a sub-folder per application. · 2024 · GACLESS + check-connection page · `doc`
- **Headless alternative** (Tekla without UI): `Tekla.Structures.Service.TeklaStructuresService(binDir, "ENGLISH", envIni, roleIni).Initialize(modelDir, "Full")` in the sample, with a custom `TeklaStructures.ini` (`XS_LICENSE_SERVER_HOST`, `XS_DEFAULT_LICENSE`), `AppDomain.AssemblyResolve` loading from Tekla `bin`, 2021 and 2026 projects only; **Flex licensing only**; cannot run in a debugger. `Tekla.Structures.Service` 2024.0.x exists on NuGet but no 2024 headless sample was found. · 2021/2026 · HeadlessTeklaStructuresExample · `sample-code`
- **Events**: `Events.TeklaStructuresExit` exists (used in a 2024 WPF sample); `Events.UndoClicked` since 2024 (TTSD-58261). Not needed for a one-shot CLI. · 2024 · SAMPLES `2024` `WpfBeamApplication/App.xaml.cs`; REL24 · `sample-code` / `doc`

## 3. Version compatibility (2024 -> 2025 -> 2026)

- **Official rule (closest statement)**: "Tekla Open API libraries are backwards compatible." Target the **oldest** supported API that works for your extension; upgrade only when you need a newer Open API; avoid internal APIs (they "usually change between versions"). It does **not** say "rebuild per version" nor state a forward guarantee for an exe built against 2024 running on 2026. · 2024+ · GACLESS · `doc`
- **Binding redirects**: Tekla-generated configs redirect `0.0.0.0-2099.1.0.0` to the running Tekla version and set `codeBase`; "any other bindings will remain untouched" so own redirects can be added. This is the mechanism that lets one build load a different Tekla version's DLLs. · 2024+ · GACLESS · `doc`
- **Evidence it works across versions**: Trimble's multi-version sample compiles a driver once against `Tekla.Structures.Model 2021.0.0` and runs it against other installed versions (2022, 2023, 2026 shown) by re-patching the config per version; for versions < 2024 it patches without `codeBase`, from 2024 with `codeBase`. Technique demonstration, not a guarantee. · 2021-2026 · MultiTeklaStructuresMonitor (`DriverStarter.cs`, `TeklaGrpcApiService.csproj`) · `sample-code`
- **Safe plan**: one `TeklaCore` per target major version (2024 now), rebuilt per version with the matching NuGet version; do not rely on forward compatibility until tested (To verify #4).
- **Runtime of Open API**: 2024: .NET Framework 4.8, libraries also .NET Standard 2.0 compatible, COM support removed, assemblies no longer in the GAC, communication "at least two times faster", targeting older .NET Framework no longer possible. 2025: no runtime change noted; CustomPropertiesPlugin became NetStandard2.0-compatible. 2026: no .NET change; Open API extensions "support only 64-bit platforms" (TTSD-73016); Tekla 2026 requires Windows 11 x64, no ARM. All three still require .NET Framework 4.8. · REL24 / REL25 / REL26; system requirements pages · `doc`
- **Windows**: 2024 Windows 10 (64-bit) and 11; 2025 Windows 11 only; 2026 Windows 11 (64-bit) only. · system requirements pages · `doc`
- **Breaking/notable changes**:
  - 2024: Gacless; COM removed; old drawing colour properties obsolete (use TrueColor); `GetRebarComplexGeometries` overload without `simplified` deprecated. (REL24 · `doc`)
  - 2025: Developer Kit (RPC) **breaks binary compatibility** (source compatible; recompile RPC components; TTSD-18961); Matrix multiplication order changed (TTSD-64773, swap `B*A` to `A*B`); `CatalogHandler.ImportShapeItemsFromGeometryFiles` added; report property values for several objects in one call (TTSD-66148, `Model.GetReportPropertyStr/Int/Double(IList<Identifier>, string)`). (REL25 · `doc`)
  - 2026: x64-only; `Tekla.Structures.Model` NuGet netstandard2.0-only with 13 extra transitive packages (Microsoft.Extensions.Logging 9.0.6, Newtonsoft.Json 13.0.4, ...); `CreateNCFilesFromSelected` now returns false when numbering is out of date (TTSD-70766); new `ModelSharingHandler`, `Operation.CreateIFC2x3Export`, `CreateReport(ReportParameters)`, `Beam.StartLevelName/EndLevelName/...`, `ContourPlate.LevelName/LevelOffset`, `ModelObject.GetCustomObjectType/SetCustomObjectType`, `ModelObjectEnum.BUILDING_SITE`. (REL26 `doc`; additions from the XML doc diff `nuget-metadata`)
- **Public-API diff on the classes this CLI uses** (documented members in the shipped XML, `Model`, `ModelObject`, `Beam`, `ContourPlate`, `Grid`, `ModelHandler`, both `ModelObjectSelector`s, `ModelObjectEnumerator`, `ModelInfo`, `Operation.Create*/Run*/Save*`): **0 members removed, 17 added from 2024.0.4 to 2026.0.3.** Caveat: compares documentation members, not the binary surface; IFC4 export methods gained overloads in 2026 (old signatures still documented). · 2024->2026 · PKG24 vs PKG26 XML · `nuget-metadata`
- **Model files** are not backward compatible (a model saved in 2025/2026 cannot be opened in older versions). Do not let a newer Tekla open/save the 2024 test model by accident. · 2025/2026 · https://support.tekla.com/doc/tekla-structures/2025/rel_cover, 2026 release notes (search-result text only; page not fetched) · `secondary`

## 4. Edition / licence

- **Open API in Diamond**: yes. The subscription feature map has an **"Open API capabilities" row ticked for Carbon, Graphite, Diamond** (2024 page) and for **Diamond, Graphite, Carbon, Trial** (2026 page), with no footnote on that row. Diamond = "for detailing and production information"; its column is ticked on every row. · 2024, 2026 (2025 not fetched) · https://support.tekla.com/doc/tekla-structures/2024/ts_configurations ; https://support.tekla.com/doc/tekla-structures/2026/ts_configurations · `doc`
- **Footnotes that matter for a modelling CLI**: Carbon: components "conceptual only"; Graphite/Carbon: numbering not available for steel/precast assemblies and CNC/MIS export only for models already numbered in Diamond; Trial: printing and exporting drawings disabled. Not Open API specific. · 2024/2026 · same pages · `doc`
- **Configurations without Open API**: none listed in the current subscription maps. Legacy on-premises map (2021 page): Open API ticked for all 11 listed configurations (Full, Steel Detailing, Precast Concrete Detailing, Rebar Detailing, Engineering, Construction Modeling, EPM Modeler, Primary, Production Planner for Concrete, Project Viewer, Drafter) with Drafter marked "View only". "Partner" configuration is for application/BIM-content development only (no modelling/detailing); I read this from a search summary of https://support.tekla.com/doc/tekla-structures/not-version-specific/admintool_about_tekla_stuctures_subscriptions, page not fetched. · 2021 (legacy) · https://support.tekla.com/doc/tekla-structures/2021/ts_configurations · `doc` / `secondary`
- **Licence to develop**: "You need a Tekla Structures license to develop with the Tekla Open API." Commercial developers buy a Tekla Partners Program Suite licence; students use Tekla Structures Learning; 30-day trial exists. · 2025-08 page · https://developer.tekla.com/documentation/get-started-tekla-structures-open-api · `doc`
- **Redistributing NuGet DLLs / the built tool**: the packages carry Trimble's EULA (`TRIMBLE-TEKLA-EULA-2022`, identical text in 2024 and 2026 packages), `requireLicenseAcceptance=true`, `licenseUrl` deprecated, projectUrl tekla.com. EULA 4.11 forbids, among others, (c) making the Software "available to any third party", (f) using the Software "to develop other software, except the Applications", (g) developing Applications **for third parties without Trimble's Partner Program/Partner License**. Clause 15.4 lets Partner licensees distribute Applications to customers. The EULA does not name NuGet DLLs explicitly. **Internal use of a tool built by the licensed company is the intended use; shipping the tool or the DLLs outside the company needs a Partner licence and legal review.** · 2024/2026 · PKG24 `eula.txt` clauses 4.11, 15 · `nuget-metadata`

## 5. API map per subcommand

Namespaces: `Tekla.Structures` (`Identifier`, `TeklaStructuresInfo`, `TeklaStructuresSettings`), `Tekla.Structures.Model` (`Model`, `ModelObject`, `Beam`, ...), `Tekla.Structures.Model.UI` (`ModelObjectSelector`), `Tekla.Structures.Model.Operations` (`Operation`), `Tekla.Structures.Catalogs`, `Tekla.Structures.Filtering(.Categories)`, `Tekla.Structures.Geometry3d`. Source for every row: PKG24 shipped XML (member ID shown) unless another source is named; status `nuget-metadata`. Behaviour beyond the XML text is unverified (see To verify). Applies to: 2024; the same member exists in 2025 and 2026 unless noted.

### info
- Tekla version: `TeklaStructuresInfo.GetCurrentProgramVersion()` (and `GetBuildNumber()`, `GetRevisionDate()`, `GetCurrentUser()`, `GetLocalAppDataFolder()` = XSUSERDATADIR, `GetCommonAppDataFolder()` = XSDATADIR). Format of the returned string not documented. (`T:Tekla.Structures.TeklaStructuresInfo`, in `Tekla.Structures.dll`)
- Open model: `new Model().GetInfo()` -> `ModelInfo.ModelPath` ("path to the model"; folder vs file, trailing separator not documented), `.ModelName`, `.CurrentPhase`, `.SharedModel`, `.SingleUserModel`, `.NorthDirection`. `GetProjectInfo()`, `GetPhases()`.
- Catalogs available: `CatalogHandler.GetProfileItems/GetLibraryProfileItems/GetParametricProfileItems/GetMaterialItems/GetComponentItems/GetBoltItems/GetUserPropertyItems/...` return enumerators (`GetSize()` gives counts). Material catalog file referenced in docs: `XS_PROFDB\marketsizes.dat` (market sizes only).
- Advanced options / environment: `TeklaStructuresSettings.GetAdvancedOption(name, ref bool|int|string|double)` (e.g. `XS_TEMPLATE_DIRECTORY`, `XS_REPORT_OUTPUT_DIRECTORY`, `XS_MACRO_DIRECTORY`, `XS_MODEL_BACKUP_DIRECTORY` exist as Tekla options per the docs above). Use it to check preconditions.

### validate
- Profiles: `LibraryProfileItem.Select(string)` or `Select()` after setting `ProfileName`; `ParametricProfileItem.Select(string)` -> `true` on success. Alternative: loop `CatalogHandler.GetProfileItems()` (`ProfileItemEnumerator.MoveNext()` returns false on failure). Which one `Beam.Profile.ProfileString` accepts for parametric strings (e.g. `PL10*200`) vs library names is not documented: validate both paths.
- Materials: `MaterialItem.Select(name)` ("name or alias name", returns false if not found) or `MaterialItem.Exists()`.
- Components: `ComponentItem.Select(string name, int number)` (+ overload with `ComponentTypeEnum`) -> true on success; needs the component **number**, so `spec.json` must carry it. Or enumerate `GetComponentItems()`.
- UDAs defined: `CatalogHandler.GetUserPropertyItems()` / `GetUserPropertyItems(CatalogObjectTypeEnum)` -> `UserPropertyItem.Name/Type/FieldType/Level/AffectsNumbering/Unique/Visibility`. `Unique` and `AffectsNumbering` let the CLI assert `unique_attribute` and `special_flag no`. `CatalogObjectTypeEnum` includes `PART, STEEL_BEAM, STEEL_COLUMN, STEEL_CONTOUR_PLATE, CONCRETE_BEAM, CONCRETE_COLUMN, ...`.

### query
- By UDA value: `Model.GetModelObjectSelector().GetObjectsByFilter(FilterExpression)`. Build with `BinaryFilterExpressionCollection` of `BinaryFilterExpressionItem(new BinaryFilterExpression(new ObjectFilterExpressions.CustomString("RUN_ID"), StringOperatorType.IS_EQUAL, new StringConstantFilterExpression("R42")), BinaryFilterOperatorType.BOOLEAN_AND)`. `CustomString/CustomNumber/CustomBoolean/CustomDateTime(userAttribute)` exist in `ObjectFilterExpressions`, `PartFilterExpressions`, `AssemblyFilterExpressions`, `BoltFilterExpressions`, etc. String operators: `IS_EQUAL, IS_NOT_EQUAL, CONTAINS, STARTS_WITH, ENDS_WITH` (+ negations). The shipped sample builds a `BinaryFilterExpressionCollection` the same way (`ObjectFilterExpressions.Type` + `NumericConstantFilterExpression`, `Model/Applications/FilterPoursSurfacesExample/Form1.cs`, `sample-code`). **Whether `ObjectFilterExpressions.CustomString` matches UDA values on Parts specifically and whether it requires the UDA to be defined: not documented**; use `PartFilterExpressions.CustomString` for parts and test.
- Alternative: saved filter by name `GetObjectsByFilterName(name)`, `GetFilteredObjectsWithType(type, filterName)`; typed enumeration `GetAllObjectsWithType(ModelObjectEnum)`; brute force `GetAllObjects()` then `GetUserProperty("LOT", ref s)` (slow on large models).
- Enumerator: `ModelObjectEnumerator` (`MoveNext/Current/GetSize`). **"Select" in this API = load data from the database, not UI selection.** `SelectInstances=false` skips loading when only report properties are read; `AutoFetch` prefetches. Docs warn against changing `SelectInstances` normally.
- By GUID: `Model.GetIdentifierByGUID(string)` (null if not found) -> `Model.SelectModelObject(Identifier)` (null if missing or load failed). Batch: `Model.FetchModelObjects(List<string> guids, bool selectInstances)` returns an **empty list if any object does not exist**; the `List<Identifier>` overload **skips** missing objects. `Identifier.GUID` / `.ID`. Setting `GUID` on an `Identifier` resets `ID` to 0 and vice versa.
- Read UDAs: `GetUserProperty(name, ref string|double|int)` returns bool; `GetAllUserProperties(ref Hashtable)`. Report properties: `GetReportProperty(name, ref ...)`; many objects at once: 2025+ `Model.GetReportPropertyStr/Int/Double(IList<Identifier>, string)` (REL25 TTSD-66148).
- Applies: all.

### selected
- `new Tekla.Structures.Model.UI.ModelObjectSelector().GetSelectedObjects()` -> `ModelObjectEnumerator` of objects selected in the model view. Same class sets selection: `Select(ArrayList[, showDimensions[, suppressCallbacks]])` returns bool. Note the name clash with `Tekla.Structures.Model.ModelObjectSelector` (alias the UI one). `UI.ModelObjectSelector.SELECT_MAX_SIZE` exists ("max elements in one function call"; value not in docs: chunk selections).

### export
- **Report (CSV-ish)**: `Operation.CreateReportFromSelected(template, file, title1, title2, title3)` / `CreateReportFromAll(...)` (returns bool "if the report is created"; template name and file name each > 3 chars; `ArgumentException` otherwise; `DisplayReport(file)`). 2026 adds `CreateReport(ReportParameters)` with `IsFromSelected`, `XLTXFileName`, `XLSXFlags`. Output format is determined by the **template** (`.rpt` made in Template Editor; CSV-style templates use `*.csv.rpt` and `sep=;` header row advice). (PKG24/PKG26 XML `nuget-metadata`; https://support.tekla.com/doc/tekla-structures/2026/rep_tips_for_templates_and_reports `doc`). Needs a company template or one we ship in the model folder.
- **Deterministic CSV in code**: read properties per object with `GetUserProperty` / `GetReportProperty` and write the CSV in `TeklaCore`; no template dependency, no UI selection, no async. Recommended for `export` of lot/run tags. (`nuget-metadata`)
- **IFC**: 2024/2025: `Operation.CreateIFC4ExportFromSelected(fullPathAndFileName, IFCExportViewTypeEnum exportView, IEnumerable<string> propertySets, ExportBasePoint locationBy, string exportLayersAs, string objectColoring, IFCExportFlags flags, string basePointGuid)` and `CreateIFC4ExportFromAll(...)`; `ValidateIfc4ExportInputParameters(...)`. Output `.ifc` or `.ifcZip`; returns false on failure "see session log". View types: `REFERENCE_VIEW, DESIGN_TRANSFER_VIEW, PRECAST_VIEW, MEP_REFERENCE_VIEW, MEP_DESIGN_TRANSFER_VIEW, BRIDGE_VIEW, UNDEFINED`. Property-set XML paths in the sample are relative to the Tekla environment (`..\default\General\Shared\IFC\AdditionalPSets\...`). 2026 adds `IFCExportVersionEnum` overloads, `CreateIFC4ExportFromSelectedAndTheirAssemblies`, and **`CreateIFC2x3Export`** (absent in 2024/2025 XML). **IFC2x3 in 2024 = macro/UI, not found as API.**
- Both selected-based exports require setting the UI selection first (sample does `MOS.Select(Parts)` then `MOS.Select(new ArrayList())` afterwards to clear).
- Other exports present: `CreateNCFilesFromSelected/All` (NC settings name + folder), `CreateDGNv8Export`, `CreateMISFileFrom*`. Not needed.
- `RunMacro(fileName)`: macros are `*.cs` files in `XS_MACRO_DIRECTORY`; throws if not found; `IsMacroRunning()` for polling (the CNC sample polls it).
- "Writes files, not the model" is true, but it changes UI selection state (not model data).

### build
- **Beam**: `new Beam(Point start, Point end)` or `new Beam(Beam.BeamTypeEnum)`; `Beam.Profile.ProfileString = "HEA400"`, `Beam.Material.MaterialString = "S235JR"`, `Name`, `Class`, `Finish`, `Position` (`Part.*`), `StartPoint/EndPoint`. `Insert()` returns bool ("All the attributes must be set"). Units: model units (mm) in all samples. Sample: Trimble `BeamApplication` (2024). · `nuget-metadata` + `sample-code`
- **Column**: **there is no `Column` class.** A column is a `Beam` with `Beam.BeamTypeEnum.COLUMN` (enum also has `BEAM, PANEL, STRIP_FOOTING, PAD_FOOTING`; footings valid for concrete only), start/end points vertical. Catalog object types `STEEL_COLUMN`/`CONCRETE_COLUMN` are for attribute lookup.
- **ContourPlate**: `new ContourPlate()`; `AddContourPoint(new ContourPoint(Point, Chamfer))` returns false "if there is no more space for another contour point"; or fill `Contour.ContourPoints`; set `Profile.ProfileString` (e.g. `PL10`), `Material`; `Insert()`.
- **Grid**: `new Grid()` defaults `Name="Grid", CoordinateX="0.00 4*3000.00", CoordinateY="0.00 5*6000.00", CoordinateZ="0.00 6000.00 8000.00 9000.00", LabelX="A B C D E", LabelY="1 2 3 4 5 6", LabelZ="+0 +6000 +8000 +9000"`, extensions 2000.0, `IsMagnetic=false`; `Insert()` returns bool. A grid is a model object: tag it too or exclude it from rollback explicitly.
- **Insert semantics**: returns `bool`; docs say nothing about partial failure, exceptions, invalid profile handling or the resulting `Identifier` timing. After success `obj.Identifier.ID/GUID` should be populated (the Component sample prints `myComponent.Identifier.ID` after `Insert()`; verify GUID is populated for Beam). Component: `new Component{Name, Number}`, `SetComponentInput(ComponentInput)`, `LoadAttributesFromFile("standard")`, `SetAttribute(name, value)`, `Insert()`.
- **UDA write**: `ModelObject.SetUserProperty(name, string|double|int)` returns bool "if the property was set successfully"; `SetUserProperties(...)` sets many at once. Insert first, then set, then `Modify()`: a **secondary** blog reports silent failure if set before `Insert()` (https://tek1.com.au/tekla-api/why-arent-the-user-defined-attributes-being-defined-in-teklas-open-api · `secondary`); the official XML says nothing about ordering. Check the bool and read back.
- **Commit**: `Model.CommitChanges(string message)` ("one commit is something that a user can later undo"; redraws changed views). Parameterless `CommitChanges()` has a doc remark "Deprecated since TS v2018": use the string overload. Plug-ins must not commit; stand-alone tools must ("non-dependent plug-ins require a separate commit if new objects are created"). One `CommitChanges` per command satisfies safety rule 5.
- `ModelObject.Insert()` doc: "The inserted instance must be of real type."

### update / rollback
- `ModelObject.Select()` (needs `Identifier` set), modify properties, `Modify()` returns bool; `Delete()` returns bool. Per-class `Beam.Modify()` "modifies the existing beam to match the current one"; `ContourPlate.Modify()` requires the identifier. Operations: `Operation.MoveObject/CopyObject/Split/Combine`.
- **Transactions / undo / rollback through the API: none.** (section Summary 1). Events: `ChangeData.ChangeSourceTypeEnum.UNDO_REDO, ROLLBACK` are event-source enum values for change events, not callable operations.
- **Recommended rollback strategy** (unverified design built on the above):
  1. `build`: create objects, record `Identifier.GUID` of each in a run journal (JSON) *before* tagging; tag; `CommitChanges("RUN_ID ...")` once at the end.
  2. On error before commit: `Delete()` every recorded GUID (re-fetch with `FetchModelObjects(List<Identifier>)`), then `CommitChanges`; if anything cannot be deleted, exit 4 and tell the engineer to restore the backup.
  3. `rollback --run-id R`: query by `RUN_ID` filter, `Delete()` each, one commit. Cross-check the count against the run journal. Gate the "restore backup" path behind the engineer.
  4. `update`: before the first `Modify()` store a before-image (all spec-relevant properties + UDAs) in the journal; on error write them back.
  5. The user's *Undo* in the UI is a manual fallback only: one `CommitChanges` is one undo step.
- Selection filters and deletion of dependent objects (welds, bolts, components attached to parts) are not covered by the docs: `Delete()` of a part may remove attached objects; verify before relying on counts.

### backup / model safety
- Check the open model path: `Model.GetInfo().ModelPath` (+ `ModelName`), compare with the project's declared working copy and refuse if equal to the original (contract rule 1). Normalise path casing/separators in code.
- Save: `new ModelHandler().Save(comment, user)` / `Save(comment, user, reason)`; `IsModelSaved()` tells whether there are unsaved changes. Comment/user "used only with multi-user models". **No SaveAs/copy** (Summary 2).
- `ModelHandler.Open(folder, openAutoSaved)` opens another model *without saving* the current one; `Close()`. Never call these from the CLI (they could discard the engineer's work).
- UI backup facts (for the macro/manual route): *Save and create backup copy* writes `..\TeklaStructuresModels\backup\<model_name>\<date-time>` (location changeable with `XS_MODEL_BACKUP_DIRECTORY`), same GUIDs as the original; restore = replace the model folder contents or rename the dated folder. (https://support.tekla.com/doc/tekla-structures/2024/mod_saving_model_with_different_name_or_location · `doc`)
- 2026 only: `ModelSharingHandler` (Model Sharing operations incl. `CreateBaselineAsync`); not for 2024.
- Internal only: the 2024 XML lists `Tekla.Structures.ModelInternal.Operation.dotSaveAsModel` and `dotSaveOperation_t.aSaveAsPath`, plus the event `Events.ModelSaveAs`. `ModelInternal` is not public API ("internal APIs usually change between versions", GACLESS); do not build the backup on it. · 2024 · PKG24 XML · `nuget-metadata` (reviewer spot-check)

## 6. UDAs (`LOT`, `RUN_ID`, `SPEC_ID`)

- **Definition mechanism**: UDAs are defined in `objects.inp` files read from the model folder, then `XS_PROJECT`, `XS_FIRM`, `XS_SYSTEM`, `XS_INP`; merged at start-up; for duplicate names the **first read wins**. Create own UDAs in an `objects.inp` in the model/project/firm folder (suffix allowed, e.g. `objects_precast.inp`); **do not copy the global file** in `..\environments\common\inp\`. · 2024 · https://support.tekla.com/doc/tekla-structures/2024/sys_customizing_uda · `doc`
- **`environment.db`**: the model stores the UDA definitions it uses in `environment.db`. New model: definitions copied from `objects.inp`. Later additions are saved when the model is opened. **Edits to existing `objects.inp` definitions are not applied automatically**; on conflict "the definitions in environment.db are used". Update an existing model via *File > Diagnose & repair > Diagnose and change attribute definitions*. Do not edit `environment.db` directly. · 2024 · sys_customizing_uda above (consistent with the zh-hans 2024 example page https://support.tekla.com/zh-hans/doc/tekla-structures/2024/sys_example_creating_and_updating_uda) · `doc`
- **Name rules**: case-sensitive; max **19 characters** (only first 19 read); no spaces or reserved characters (reserved list not given); one definition per name (not different per object type); avoid changing `value_type` of an existing UDA (create a new one). `LOT`, `RUN_ID`, `SPEC_ID` fit the length rule; clash check against the global `objects.inp` is still open (contract Open questions). · 2024 · https://support.tekla.com/doc/tekla-structures/2024/sys_objects_inp_properties ; sys_customizing_uda · `doc`
- **Definition line** (format from the docs): `attribute("NAME", "Label text", value_type, "%s", special_flag, none, "0.0", "0.0") { value("", 0) }`; `unique_attribute` instead of `attribute` = never copied to another part; `special_flag yes` on a part = considered in numbering. `value_type` examples: `string, option, integer, float, date`. A UDA must also be referenced from an object section/tab page (`modify (1)`) to appear in the properties dialog (zh-hans example). · 2024 · `doc`
- **Is a definition required for `SetUserProperty` to persist / for filters to work?** The official pages describe definitions but never say what `SetUserProperty` does with an undefined name; `GetUserPropertyItems` lists defined ones. The only statement on silent failure is a `secondary` blog about calling it before `Insert()`. **Not documented: verify on the test model** (To verify #5, #6). Plan: define all three in the company/model `objects.inp`, run Diagnose-and-change on the test model, and make `info`/`validate` fail with exit 3 when `GetUserPropertyItems()` lacks any of them.
- **Typing**: pick `string` (`%s`) for all three; `SetUserProperty(string,string)` overload exists. Do not change types later.
- Applies: all versions (2025/2026 pages not re-read).

## 7. Testing

- **Without a running Tekla**: nothing in the Open API is documented as usable offline. The official examples all start Tekla and open an empty model; Trimble's unit-test guidance (GACLESS) relies on `TSAppConfigPatcherTask` generating a config so tests run from Visual Studio Test Explorer **against an installed/running Tekla**. · 2024 · GACLESS · `doc`
- `Tekla.Structures.Model.dll` references `Trimble.Remoting` and has remoting service types, so `Model`, `Beam` etc. are proxies to the Tekla process. Pure value types (`Point`, `Vector`, `Identifier`, `Distance`, filter expression classes) may be constructible without Tekla but this is **unverified**. · 2024 · PKG24 DLL metadata strings · `nuget-metadata`
- No official guidance on mocks/fakes found. **Recommended design (our own, not Trimble's)**: keep spec parsing, validation against a catalog snapshot, tag logic, journal/rollback planning, CSV writing and exit-code mapping in a Tekla-free assembly (netstandard2.0 or net48 without Tekla references) behind small interfaces (`IModelGateway`, `ICatalogGateway`) with an in-memory fake; unit-test that on any machine (and on Linux with `dotnet test` if the project multi-targets). Only the thin adapter that calls Tekla types is integration-tested on the Tekla machine with the empty test model and `Tekla.Structures.*` references.
- Whether `Tekla.Structures.*` assemblies load at all on a non-Tekla/Linux machine: not researched. Plan CI around the Tekla-free assembly only.

---

## Version matrix

| | 2024 (company) | 2025 | 2026 |
|---|---|---|---|
| Tekla runtime / Open API runtime | .NET Framework 4.8 | .NET Framework 4.8 | .NET Framework 4.8 |
| Windows | 10 (64-bit), 11 | 11 | 11 (64-bit), no ARM |
| `Tekla.Structures.Model` NuGet | 2024.0.0 - **2024.0.4** | 2025.0.0 (beta001 earlier) | 2026.0.0, .0.2, **.0.3** |
| Package TFMs | net48 + netstandard2.0 | net48 + netstandard2.0 | netstandard2.0 (Model); net48 + netstandard2.0 (`Tekla.Structures`) |
| DLL bitness | AnyCPU | AnyCPU | x64 only |
| AssemblyVersion | 2024.0.0.0 | 2025.0.0.0 | 2026.0.0.0 |
| Key deps (Model) | Remoting 1.0.2, Geometry 4.6.2, Serialization 4.1.1 | Remoting 4.0.8, Geometry 4.6.4, Serialization 4.3.7 | Remoting 4.0.8, Geometry 4.7.0, Serialization 4.3.7, Newtonsoft.Json 13.0.4, M.E.Logging 9.0.6, +9 others |
| Assembly loading | Gacless; exe.config codeBase + redirect; `TSAppConfigPatcherTask` 2.1.x | same | same |
| Compatibility rule (Trimble) | "libraries are backwards compatible"; target oldest working; upgrade only when needed | same | same; x64-only |
| Notable changes | Gacless, COM removed, TrueColor, `Events.UndoClicked`, IFC4 export API | RPC binary break, matrix order, bulk report properties | x64-only, `ModelSharingHandler`, `CreateIFC2x3Export`, `CreateReport(ReportParameters)`, NC export returns false if numbering stale |
| Tekla service packs (as of 2026-10-15) | SP1-SP13 | SP1-SP11 | SP1-SP5 |
| IFC API | IFC4 only | IFC4 only | IFC4 + IFC2x3 |

Sources: nuspecs/DLLs (PKG24/25/26), REL24-26, system requirements pages, release-notes summary page.

---

## To verify on the test model

1. After build, does `tekla-cli.exe.config` carry the `codeBase` entries and does `new Model()` connect from a Release build run from the build folder, with Tekla 2024 open?
2. With Tekla not running: does `new Model()` throw or does `GetConnectionStatus()` return false (and how long does it block)?
3. Tekla open but CLI run elevated vs not, as a different Windows user, and with two Tekla 2024 sessions open: which session does `Model()` bind to, and what is the error?
4. Build against 2024.0.4, run against Tekla 2025/2026 with a re-patched config (version pin test) if the company upgrades.
5. `SetUserProperty` for a name **not** defined in any `objects.inp`: returns true/false? Persists after save and reopen? Visible to `GetUserProperty` and to a `CustomString` filter?
6. `SetUserProperty` before vs after `Insert()`; before vs after `Modify()`; string vs integer overloads for `RUN_ID`.
7. `ObjectFilterExpressions.CustomString("LOT")` vs `PartFilterExpressions.CustomString("LOT")` on a Beam and on a ContourPlate: which returns the objects? Does a Grid carry UDAs?
8. `Insert()` with an unknown profile or material: returns false, throws, or inserts with a default? Is `Identifier.GUID` populated right after `Insert()` (before `CommitChanges`)?
9. If the process dies/exits after `Insert()` and before `CommitChanges()`: is the object in the model? Does `Delete()` + `CommitChanges()` leave a clean model and one undo step?
10. `Delete()` on a part with attached welds/bolts/components: are dependents removed? Do those dependents carry the UDAs?
11. `ModelInfo.ModelPath` exact format (folder, trailing `\`, casing) and `TeklaStructuresInfo.GetCurrentProgramVersion()` output on 2024 (service pack visible?).
12. `UserPropertyItem.Unique` / `AffectsNumbering` values for the three UDAs after defining them as `unique_attribute` / `special_flag no`.
13. Backup route: does `Operation.RunMacro` of a macro that issues *Save and create backup copy* work against the open model? Does `ModelHandler.Save` followed by a file-copy of the model folder open correctly? Does a copy keep GUIDs? Where does `XS_MODEL_BACKUP_DIRECTORY` point on this machine?
14. `CreateReportFromSelected` synchronous or not; template location; CSV content; does `CreateIFC4ExportFromSelected` honour the UI selection of 1 part; clear selection afterwards works.
15. `FetchModelObjects(List<string>)` with one unknown GUID returns empty as documented; compare against the `Identifier` overload.
16. `UI.ModelObjectSelector.Select` with more than `SELECT_MAX_SIZE` objects.
17. Whether the CLI needs `CommitChanges` after read-only selection changes (the XML examples call it after `Select`).
18. `GetObjectsByBoundingBox` is "NOT EXACT"; not to be used for lot queries (documented), confirm by test if ever needed.
19. Can the CLI run while the Tekla UI is in a modal dialog or busy (macro running via `IsMacroRunning`)?
20. (ADR-0012) A UDA filter on parts (`LOT`, `RUN_ID`, `SPEC_ID`) returns exactly the tagged objects, including just-inserted uncommitted ones.
21. (ADR-0012) `GetIdentifierByGUID` (or the chosen lookup) tells "not found" apart from a failure, for a deleted, a never-existing and an uncommitted object.
22. (ADR-0012) Beam start/end come back in global mm once the global `TransformationPlane` is set, whatever work plane the UI shows.
23. (ADR-0012) Profile and material strings read back exactly as written by `Insert` (no normalisation such as `HEA300` → `HEA 300`); rotation read back in the same convention as written.
24. (ADR-0012) A string UDA holds a 64-character `SPEC_ID` without truncation.
25. (ADR-0012) Setting the three UDAs before `Insert` works and persists (would remove the intent window).

## Gaps

- **NuGet patch -> Tekla service pack mapping** for 2024.0.0-2024.0.4: looked at NuGet pages, release-notes summary (first 100k of ~167k chars), developer news. Not found.
- **Official forward-compatibility guarantee** (app built on 2024 running on 2025/2026): looked at GACLESS, REL24-26, developer news. Only "backwards compatible" (libraries) found. The Open API 17.0 release note statement on frozen classes came up in a search summary but the page was not fetched.
- **Connection failure modes** (version mismatch, user/elevation mismatch, which instance `Model()` binds to when several same-version sessions run): looked at check-connection page, how-Open-API-works page (does not cover remoting), multi-session support article (first session only), samples. Not found. The old Trimble-Remoting transport (named pipe/TCP) is not documented in the pages read.
- **2026 product bulletin** (x64-only): only the public summary readable; "Impacted Extensions" text and any rebuild/AnyCPU guidance are behind a Trimble login.
- **Copy Local / `ExcludeAssets="runtime"` guidance** for stand-alone exes: not in GACLESS or the check-connection page; Trimble samples reference packages normally (copy local default) and patch config.
- **UDA behaviour in the API** (undefined name, order vs `Insert`): not in the support pages, XML docs or samples read.
- **Transaction/undo API**: searched XML docs of Model 2024/2026 for SaveAs/Backup/Undo/Transaction/Rollback; only events found. No macro/akit callback documentation fetched.
- **Official unit-testing guidance** without Tekla: searched developer.tekla.com; nothing beyond integration tests with the patcher.
- **IFC2x3 export in 2024 via API**: absent from the 2024/2025 XML; macro/UI route not researched.
- **Tekla 2025 configuration page** and the **admin subscription page** were not fetched (2024, 2026, 2021 were; Partner caveat from a search summary only).
- **developer.tekla.com per-method reference URLs** (numeric IDs) were not collected; the package XML member IDs above are the citation. The 2026 `Model` and `ModelHandler` class pages were fetched: https://developer.tekla.com/doc/tekla-structures/2026/model-class-71942, https://developer.tekla.com/doc/tekla-structures/2026/model-handler-class-71964.
- **Model API intro PDF** (https://developer.tekla.com/sites/default/files/files/download-file/file/4%20-%20Model%20API%20introduction,%20tips%20and%20FAQ.pdf): fetched, mostly slide images, no usable tips extracted.
- **Tekla Developer Assistant** (Preview in 2025, AI code helper for macros) exists; not evaluated.
