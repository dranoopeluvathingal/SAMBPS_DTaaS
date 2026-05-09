function run_smoke()
%RUN_SMOKE  Run the matlab/tests/ suite and exit with the test-result code.
%
%   Suitable for `matlab -batch "addpath('matlab'); run_smoke"` invocation
%   in CI.  Bootstraps the path via STARTUP_FAULTLOC, runs every test in
%   matlab/tests/, prints a summary, and exits with code 0 on full pass
%   or code 1 if any test failed or was incomplete.

    startup_faultloc;

    here = fileparts(mfilename('fullpath'));   % .../fault_location_id/matlab
    test_dir = fullfile(here, 'tests');

    fprintf('\nRunning matlab/tests/ ...\n');
    results = runtests(test_dir);

    fprintf('\nTest summary:\n');
    for k = 1:numel(results)
        fprintf('  %-40s passed=%d failed=%d incomplete=%d duration=%.3fs\n', ...
                results(k).Name, results(k).Passed, results(k).Failed, ...
                results(k).Incomplete, results(k).Duration);
    end

    failed = any([results.Failed]);
    incomplete = any([results.Incomplete]);
    code = double(failed || incomplete);

    if code == 0
        fprintf('matlab smoke: PASS\n');
    else
        fprintf(2, 'matlab smoke: FAIL (failed=%d, incomplete=%d)\n', ...
                failed, incomplete);
    end

    exit(code);
end
