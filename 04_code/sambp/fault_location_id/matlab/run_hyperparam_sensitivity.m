function run_hyperparam_sensitivity()
%RUN_HYPERPARAM_SENSITIVITY  WP0.4 sub-task 4 - 9-cell sensitivity sweep.
%
%   Sweeps the central-difference step h_alpha and the Armijo
%   backtracking ratio beta over a 3 x 3 grid:
%       h_alpha in {1e-3, 1e-4, 1e-5}
%       beta    in {0.3, 0.5, 0.7}
%   For each grid cell, runs faultloc_optimiser on every cell of the
%   720-case dataset and reports the mean relative location error.
%
%   Writes outputs/phase0_hyperparam_sensitivity.csv with columns:
%     h_alpha, beta, mean_loc_err_pct, n_cases

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    addpath(fullfile(here, 'utils'));

    data_path = fullfile(here, 'data', 'dataset_720.mat');
    if ~isfile(data_path), build_dataset(data_path); end
    S = load(data_path);

    h_alpha_grid = [1e-3, 1e-4, 1e-5];
    beta_grid    = [0.3, 0.5, 0.7];

    out_dir = fullfile(here, '..', 'outputs');
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end
    out_path = fullfile(out_dir, 'phase0_hyperparam_sensitivity.csv');
    fid = fopen(out_path, 'w');
    fprintf(fid, 'h_alpha,beta,mean_loc_err_pct,n_cases\n');

    for ih = 1:numel(h_alpha_grid)
        for ib = 1:numel(beta_grid)
            opts = struct('h_alpha', h_alpha_grid(ih), ...
                          'beta',    beta_grid(ib));
            N = numel(S.H_meas);
            errs = zeros(N, 1);
            for n = 1:N
                theta_hat = faultloc_optimiser(S.H_meas(n), opts);
                errs(n) = abs(theta_hat(1) - S.grid_alpha(n)) / S.grid_alpha(n);
            end
            mean_err_pct = 100 * mean(errs);
            fprintf('  h_alpha=%.0e  beta=%.1f  mean loc err = %.4f %%\n', ...
                    h_alpha_grid(ih), beta_grid(ib), mean_err_pct);
            fprintf(fid, '%.0e,%.1f,%.6f,%d\n', ...
                    h_alpha_grid(ih), beta_grid(ib), mean_err_pct, N);
        end
    end

    fclose(fid);
    fprintf('  wrote %s\n', out_path);
end
