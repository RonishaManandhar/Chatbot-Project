/*!
 * Sidebar menu for Bootstrap 4
 * Fixed for nested sidebar links
 */
(function ($) {

    // Toggle sidebar
    $("#sidebar-toggle").on("click", function (e) {
        e.preventDefault();
        $("#wrapper").toggleClass("sidebar-toggle");
    });

    // Open current active menu only
    $(".link-current").each(function () {
        const currentLink = $(this);

        if (currentLink.hasClass("link-arrow")) {
            currentLink.addClass("active down");
            currentLink.next(".list-hidden").show();
        }
    });

    // Only dropdown parent should open/close
    $(".link-arrow").on("click", function (e) {
        e.preventDefault();

        const link = $(this);
        const submenu = link.next(".list-hidden");

        link.toggleClass("active rotate");
        submenu.slideToggle("fast");
    });

})(jQuery);