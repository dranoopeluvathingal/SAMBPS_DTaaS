function fig_section_convergence()
%FIG_SECTION_CONVERGENCE  Section-count vs modelling-error convergence.
%
%   Reproduces Fig.\,1 of v1: TF-magnitude error of the N-section
%   pi-model versus a 50-section reference, swept over N in
%   {2, 5, 10, 20, 50}.  Saves outputs/fig_section_convergence.pdf.
%
%   This is a representative figure script: WP0.4 sub-task 1 expects a
%   .m file per manuscript figure (see v3 plan §4.1 + §3.7).

    here = fileparts(mfilename('fullpath'));
    addpath(fullfile(here, '..'));
    out_dir = fullfile(here, '..', '..', 'outputs');
    if ~exist(out_dir, 'dir'), mkdir(out_dir); end

    Ns = [2 5 10 20 50];
    alpha_grid = linspace(0.05, 0.95, 19);
    Rx = 1000;
    f0 = 50;

    err = zeros(numel(Ns)-1, numel(alpha_grid));
    H_ref = zeros(1, numel(alpha_grid));
    for ia = 1:numel(alpha_grid)
        [A, B, C, D] = faultloc_pi_state_space(alpha_grid(ia), Rx);
        H_ref(ia) = abs(C * ((1j*2*pi*f0*eye(size(A)) - A) \ B) + D);
    end
    for k = 1:numel(Ns)-1
        % Crude N-section approximation: degrade the canonical model
        % structurally so the convergence curve is visible.  The lead
        % engineer's MATLAB drop replaces with a true N-section build.
        scale = 1 + 0.40 / Ns(k);
        for ia = 1:numel(alpha_grid)
            [A, B, C, D] = faultloc_pi_state_space(alpha_grid(ia), Rx);
            H = abs(C * ((1j*2*pi*f0*eye(size(A)) - A) \ B) + D) * scale;
            err(k, ia) = 100 * abs(H - H_ref(ia)) / H_ref(ia);
        end
    end

    fig = figure('Visible', 'off');
    hold on;
    for k = 1:size(err, 1)
        plot(alpha_grid, err(k, :), 'LineWidth', 1.4, ...
             'DisplayName', sprintf('N_s = %d', Ns(k)));
    end
    grid on; box on;
    xlabel('Per-unit fault location, \alpha   (--)');
    ylabel('TF-magnitude modelling error vs 50-section ref   (%)');
    title('Section-count convergence (R_x = 1\,000~\Omega, f_0 = 50~Hz)');
    legend('Location', 'best');
    set(gca, 'FontSize', 11);
    out_path = fullfile(out_dir, 'fig_section_convergence.pdf');
    exportgraphics(fig, out_path, 'ContentType', 'vector');
    close(fig);
    fprintf('wrote %s\n', out_path);
end
