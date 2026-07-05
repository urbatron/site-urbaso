

function include(scriptUrl) {
    document.write('<script src="' + scriptUrl + '"></script>');
}

function isIE() {
    var myNav = navigator.userAgent.toLowerCase();
    return (myNav.indexOf('msie') != -1) ? parseInt(myNav.split('msie')[1]) : false;
};

/* cookie.JS
 ========================================================*/
include('js/jquery.cookie.js');

/* Easing library
 ========================================================*/
include('js/jquery.easing.1.3.js');

/* PointerEvents  
 ========================================================*/
;
(function ($) {
    if(isIE() && isIE() < 11){ 
        include('js/pointer-events.js');
        $('html').addClass('lt-ie11'); 
        $(document).ready(function(){
            PointerEventsPolyfill.initialize({});
        });
    }
})(jQuery); 

/* Stick up menus
 ========================================================*/
;
(function ($) {
    var o = $('html');
    if (o.hasClass('desktop')) {
        include('js/tmstickup.js');

        $(document).ready(function () {
            $('#stuck_container').TMStickUp({})
        });
    }
})(jQuery);

/* ToTop
 ========================================================*/
;
(function ($) {
    var o = $('html');
    if (o.hasClass('desktop')) {
        include('js/jquery.ui.totop.js');

        $(document).ready(function () {
            $().UItoTop({
                easingType: 'easeOutQuart',
                containerClass: 'toTop fa fa-angle-up'
            });
        });
    }
})(jQuery);

/* EqualHeights
 ========================================================*/
;
(function ($) {
    var o = $('[data-equal-group]');
    if (o.length > 0) {
        include('js/jquery.equalheights.js');
    }
})(jQuery);

/* SMOOTH SCROLLIG
 ========================================================*/
;
(function ($) {
    var o = $('html');
    if (o.hasClass('desktop')) {
        include('js/jquery.mousewheel.min.js');
        include('js/jquery.simplr.smoothscroll.min.js');

        $(document).ready(function () {
            $.srSmoothscroll({
                step: 150,
                speed: 800
            });
        });
    }
})(jQuery);

/* Copyright Year
 ========================================================*/
;
(function ($) {
    var currentYear = (new Date).getFullYear();
    $(document).ready(function () {
        $("#copyright-year").text((new Date).getFullYear());
    });
})(jQuery);


/* Superfish menus
 ========================================================*/
;
(function ($) {
    include('js/superfish.js');    
})(jQuery);

/* Navbar
 ========================================================*/
;
(function ($) {
    include('js/jquery.rd-navbar.js');
})(jQuery);


/* Google Map
 ========================================================*/
;
(function ($) {
    var o = document.getElementById("google-map");
    if (o) {
        include('//maps.google.com/maps/api/js?sensor=false');
        include('js/jquery.rd-google-map.js');

        $(document).ready(function () {
            var o = $('#google-map');
            if (o.length > 0) {
                o.googleMap({
                    styles: [{"featureType":"water","elementType":"all","stylers":[{"hue":"#76aee3"},{"saturation":38},{"lightness":-11},{"visibility":"on"}]},{"featureType":"road.highway","elementType":"all","stylers":[{"hue":"#8dc749"},{"saturation":-47},{"lightness":-17},{"visibility":"on"}]},{"featureType":"poi.park","elementType":"all","stylers":[{"hue":"#c6e3a4"},{"saturation":17},{"lightness":-2},{"visibility":"on"}]},{"featureType":"road.arterial","elementType":"all","stylers":[{"hue":"#cccccc"},{"saturation":-100},{"lightness":13},{"visibility":"on"}]},{"featureType":"administrative.land_parcel","elementType":"all","stylers":[{"hue":"#5f5855"},{"saturation":6},{"lightness":-31},{"visibility":"on"}]},{"featureType":"road.local","elementType":"all","stylers":[{"hue":"#ffffff"},{"saturation":-100},{"lightness":100},{"visibility":"simplified"}]},{"featureType":"water","elementType":"all","stylers":[]}]
                });
            }
        });
    }
})
(jQuery);

/* WOW
 ========================================================*/
;
(function ($) {
    var o = $('html');

    if ((navigator.userAgent.toLowerCase().indexOf('msie') == -1 ) || (isIE() && isIE() > 9)) {
        if (o.hasClass('desktop')) {
            include('js/wow.js');

            $(document).ready(function () {
                new WOW().init();
            });
        }
    }
})(jQuery);

/* Contact Form
 ========================================================*/
;
(function ($) {
    var o = $('#contact-form');
    if (o.length > 0) {
        include('js/modal.js');
        include('js/TMForm.js'); 

        if($('#contact-form .recaptcha').length > 0){
        	include('//www.google.com/recaptcha/api/js/recaptcha_ajax.js');
        }
    }
})(jQuery);

/* Orientation tablet fix
 ========================================================*/
$(function () {


    //уравниваем блоки в информации
    if(screen.width>760)
    {
        $('.blog-content .grid_4 h2').equalHeights();
        $('.blog-content .grid_4 p').equalHeights();
        $('.well li').equalHeights();
        $('.gallery-container h3').equalHeights();
        $('.gallery-container p').equalHeights();
    }

    // IPad/IPhone
    var viewportmeta = document.querySelector && document.querySelector('meta[name="viewport"]'),
        ua = navigator.userAgent,

        gestureStart = function () {
            viewportmeta.content = "width=device-width, minimum-scale=0.25, maximum-scale=1.6, initial-scale=1.0";
        },

        scaleFix = function () {
            if (viewportmeta && /iPhone|iPad/.test(ua) && !/Opera Mini/.test(ua)) {
                viewportmeta.content = "width=device-width, minimum-scale=1.0, maximum-scale=1.0";
                document.addEventListener("gesturestart", gestureStart, false);
            }
        };

    scaleFix();
    // Menu Android
    if (window.orientation != undefined) {
        var regM = /ipod|ipad|iphone/gi,
            result = ua.match(regM);
        if (!result) {
            $('.sf-menus li').each(function () {
                if ($(">ul", this)[0]) {
                    $(">a", this).toggle(
                        function () {
                            return false;
                        },
                        function () {
                            window.location.href = $(this).attr("href");
                        }
                    );
                }
            })
        }
    }
});
var ua = navigator.userAgent.toLocaleLowerCase(),
    regV = /ipod|ipad|iphone/gi,
    result = ua.match(regV),
    userScale = "";
if (!result) {
    userScale = ",user-scalable=0"
}
document.write('<meta name="viewport" content="width=device-width,initial-scale=1.0' + userScale + '">');

/* Camera
========================================================*/
;(function ($) {
var o = $('#camera');
    if (o.length > 0) {
        if (!(isIE() && (isIE() > 9))) {
            include('js/jquery.mobile.customized.min.js');
        }

        include('js/camera.js');

        $(document).ready(function () {
            o.camera({
                autoAdvance: true,
                height: '30.859375%',
                minHeight: '350px',
                pagination: false,
                thumbnails: false,
                playPause: false,
                hover: false,
                loader: 'none',
                navigation: true,
                navigationHover: false,
                mobileNavHover: false,
                fx: 'simpleFade'
            })
        });
    }
})(jQuery);

/* Owl Carousel
========================================================*/
;(function ($) {
    var o = $('.owl-carousel');
    if (o.length > 0) {
        include('js/owl.carousel.min.js');
        $(document).ready(function () {
            o.owlCarousel({
                margin: 30,
                smartSpeed: 450,
                loop: true,
                dots: true,
                dotsEach: 1,
                nav: false,
                navClass: ['owl-prev fa fa-angle-left', 'owl-next fa fa-angle-right'],
                responsive: {
                    0: { items: 1 },
                    768: { items: 1},
                    980: { items: 1},
                }
            });
        });
    }
})(jQuery);

/* Mailform
=============================================
;(function ($) {
    include('js/mailform/jquery.form.min.js');
    include('js/mailform/jquery.rd-mailform.min.c.js');
})(jQuery);/*


/* Парсинг яндекс справочника и вывод информации в блок
=============================================*/
    $("#parsingKontact").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/rezultat-parsinga-kontaktov.html';
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

    /* Парсинг яндекс справочника и вывод информации в блок
=============================================*/
    $("#parsingDistanceKontact").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/parsing-kontaktov-po-radiusu.html';
        name = "name="+$(this).find("#name").val();
        number = "number="+$(this).find("#number").val();
        salon = "salon="+$(this).find("#salon").val();
        str = name + "&" + number + "&" + salon;
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: str,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

        /* Узнаем индекс по адресу
=============================================*/
    $("#parsingIndexKontact").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/uznat-pochtovyij-indeks-po-adresu.html';
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

            /* Узнаем координаты по адресу
=============================================*/
    $("#parsingKoorKontact").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/uznat-koordinatyi-x-i-y-po-adresu.html';
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

            /* Узнаем координаты по адресу
=============================================*/
    $("#parsingRaionKontact").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/uznat-rajonyi-po-adresam.html';
        
        
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

                /* Генерируем пароль
=============================================*/
    $('#parsingPasswordRezult').html(str_rand());
    $("#passwordGeneric").submit(function(e)
    {
        e.preventDefault();
        $('#parsingPasswordRezult').html(str_rand());

    })

function str_rand() {
        var result       = '';
        var words        = '0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM';
        var max_position = words.length - 1;
            for( i = 0; i < 8; ++i ) {
                position = Math.floor ( Math.random() * max_position );
                result = result + words.substring(position, position + 1);
            }
        return "<h2>"+result+"</h2>";
    }


                /* Чистим телефонную базу
=============================================*/
    $("#parsingPhoneMoscowRezult").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/poluchaem-ochishhennuyu-telefonnuyu-bazu-(moskva).html';
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })

                    /* Обрабатываем ключевые слова под заголовок1
=============================================*/
    $("#obrabotkaZagolovok1").submit(function(e)
    {
        e.preventDefault();
        var url  = location.protocol + '//' + location.host + '/podgotovka-zagolovka1-dlya-reklamnyix-kampanij-yandeks.direkt.html';
        name = "name="+$(this).find("#name").val();
        $("#parsingKontactRezult").html("<div id='p_prldr'><div class='contpre'><span class='svg_anm'></span><br>Подождите<br><small>идет загрузка</small></div></div>");
        $.ajax(
        {  
          url: url,   
          data: name,
          type: "POST",
          success:  function(data) 
          { 
            $("#parsingKontactRezult").html(data);
          },
        });
    })


                    /* В заголовке1 есть поля для продления заголовка. Добавляем еще такое поле
=============================================*/
$(".dopZagolovok .dopZagolPlus").on("click",function(){
    $(this).parent().find('input').attr('value',$(this).parent().find('input').val());
    dop = parseInt($(this).parent().find('input').attr('name').replace(/[^0-9]/gim,'')) + 1;
    $(this).parent().find('input').attr('placeholder',$(this).parent().find('input').val());
    $(this).parent().after('<div class="grid_4 dopZagolovok"><input type="text" name=dop'+dop+' id=dop'+dop+' required placeholder="Рядом с метро" style="height: 45px; width: 70%;font-size:16px;padding-left:10px"><img src="images/article/news2/icon-healthcare-providers2.png" class="dopZagolPlus" alt="add" title="Добавить еще одно поле" style="margin-top:7px; cursor:pointer"></div>');
    $(this).replaceWith('<img src="images/article/news2/icon-healthcare-minus.png" alt="minus" class="dopZagolMinus" title="Удалить поле" style="margin-top:7px; cursor:pointer">');
    $.cookie('dopPole', $('.dopContainer').html());
})

$(".dopZagolovok .dopZagolPlus").live("click",function(){
    $(this).parent().find('input').attr('value',$(this).parent().find('input').val()); 
    dop = parseInt($(this).parent().find('input').attr('name').replace(/[^0-9]/gim,'')) + 1;
    $(this).parent().after('<div class="grid_4 dopZagolovok"><input type="text" name=dop'+dop+' id=dop'+dop+' required placeholder="Рядом с метро" style="height: 45px; width: 70%;font-size:16px; padding-left:10px"><img src="images/article/news2/icon-healthcare-providers2.png" class="dopZagolPlus" alt="add" title="Добавить еще одно поле" style="margin-top:7px; cursor:pointer"></div>');
    $(this).replaceWith('<img src="images/article/news2/icon-healthcare-minus.png" alt="minus" class="dopZagolMinus" title="Удалить поле" style="margin-top:7px; cursor:pointer">');
    $.cookie('dopPole', $('.dopContainer').html());
})

//И удаляем поле
$(".dopZagolovok .dopZagolMinus").live("click",function(){
    $(this).parent().remove();
    $.cookie('dopPole', $('.dopContainer').html());
    })
        
//сохраним все содержимое дополнительных полей заголовка1
if($.cookie('dopPole')) $('.dopContainer').html($.cookie('dopPole'));
$.cookie('dopPole', $('.dopContainer').html());



                    /* сохраняем все данные form в cookie
=============================================*/
$('document').click(function(){$('form').sisyphus();});








