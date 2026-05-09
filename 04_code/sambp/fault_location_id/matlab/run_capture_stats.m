function run_capture_stats()
%RUN_CAPTURE_STATS  WP0.4 sub-task 3 - global-optimum capture + timing.
%
%   Runs faultloc_optimiser on every cell of the 720-case dataset and
%   reports:
%     (a) capture statistic = fraction of cells whose Stage-2 cost J at
%         termination satisfies J < 1e-12 (i.e. effectively bottomed out).
%     (b) wall-clock timing of the optimiser kernel: median and 95th-
%         percentile across 1000 invocations on a representative cell.
%
%   Writes outputs/phase0_capture_and_timing.csv with columns:
%     metric, value, unit, n_samples, notes

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    addpath(fullfile(here, 'utils'));

    data_path = fullfile(here, 'data', 'dataset_720.mat');
    if ~isfile(data_path), build_dataset(data_path); end
    S = load(data_path);

    fprintf('run_capture_stats: 720-case sweep starting...\n');
    N = numel(S.H_meas);
    J_min = zeros(N, 1);
    for n = 1:N
        [~, info] = faultloc_optimiser(S.H_meas(n));
        J_min(n) = info.J_min;
    end
    capture_pct = 100 * mean(J_min < 1e-12);
    fprintf('  global-optimum capture (J<1e-12): %.2f %% of %d cells\n', ...
            capture_pct, N);

    fprintf('run_capture_stats: timing 1000 calls on representative cell...\n');
    cell_rep = find( ...
        abs(S.grid_alpha - 0.5) < 1e-9 & ...
        abs(S.grid_Rx - 1000)   < 1e-9 & ...
        isinf(S.grid_SNR_V) & isinf(S.grid_SNR_I), 1);
    H_rep = S.H_meas(cell_rep);

    n_calls = 1000;
    t = zeros(n_calls, 1);
    for k = 1:n_calls
        t0 = tic;
        faultloc_optimiser(H_rep);
        t(k) = toc(t0);
    end
    t_ms = t * 1e3;
    t_med = median(t_ms);
    t_p95 = prctile(t_ms, 95);
    fprintf('  median  CPU time / call = %.2f ms\n', t_med);
    fprintf('  95th-pct CPU time / call = %.2f ms\n', t_p95);

    out_dir = fullfile(here, '..', 'outputs');
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end
    out_path = fullfile(out_dir, 'phase0_capture_and_timing.csv');
    fid = fopen(out_path, 'w');
    fprintf(fid, 'metric,value,unit,n_samples,notes\n');
    fprintf(fid, 'global_optimum_capture,%.4f,%%,%d,J<1e-12 at Stage-2 termination\n', ...
            capture_pct, N);
    fprintf(fid, 'cpu_time_median,%.4f,ms,%d,representative cell (alpha=0.5 Rx=1000 noiseless)\n', ...
            t_med, n_calls);
    fprintf(fid, 'cpu_time_p95,%.4f,ms,%d,representative cell (alpha=0.5 Rx=1000 noiseless)\n', ...
            t_p95, n_calls);
    fclose(fid);
    fprintf('  wrote %s\n', out_path);
end
